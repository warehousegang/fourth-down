"""Read licensed, season-isolated nflverse game files for outcomes only.

No all-season download, forecast feature input, training, or provider scraping.
Raw bytes and first observations are immutable and independently reproducible.
"""
import gzip
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ml.current_source import ALIASES, EASTERN, canonical, check_season, current_season, download, iso, sha, timestamp
from ml.data import ROOT
from ml.lifecycle import status

REPOSITORY = "https://github.com/nflverse/nflverse-pbp"
LICENSE = REPOSITORY + "/blob/master/LICENSE.md"
MAX_RAW = 2_000_000
MAX_EXPANDED = 5_000_000
# The supplemental provider uses an underscore for overtime finals. Keep its
# original phase in evidence; map only when applying shared lifecycle rules.
FINAL_PHASES = {'FINAL', 'FINAL OVERTIME', 'FINAL_OVERTIME'}


class ValidatedObservation(dict):
    """Original serialized evidence plus a transient interpretation of its raw file.

    The interpretation is deliberately outside the dictionary: canonical JSON,
    content addresses and first-observed timestamps remain the original bytes.
    Fresh archive restoration must validate the raw file to reconstruct it.
    """
    def __init__(self, observation, game):
        super().__init__(observation)
        self._verified_game = game
        self._evidence_sha256 = sha(canonical(observation))


def effective_game(observation):
    """Interpret a validated legacy observation without rewriting its receipt.

    Old parsers retained some explicit raw finals as unknown/unvalidated.
    validate_observation proves the original fields and reconstructs the
    interpretation from raw bytes without changing the evidence dictionary.
    """
    if isinstance(observation, ValidatedObservation):
        if sha(canonical(observation)) != observation._evidence_sha256:
            raise ValueError('Validated result observation was modified')
        return dict(observation._verified_game)
    game = observation['game']
    if game['phase'] == 'FINAL_OVERTIME' and game['status'] == 'unknown' and game['validated'] is False:
        return {**game, 'validated':True, 'status':'completed'}
    return game


def provider_id(game):
    check_season(game['season'])
    from ml.current_source import TEAMS
    if (game['home'] not in TEAMS or game['away'] not in TEAMS or game['home'] == game['away']
            or type(game['week']) is not int or not 1 <= game['week'] <= 18
            or not re.fullmatch(rf"ngs-{game['season']}-\d+", game['id'])):
        raise ValueError('Invalid current-season result identity')
    return f"{game['season']}_{game['week']:02}_{game['away']}_{game['home']}"


def source_url(game):
    return f"{REPOSITORY}/releases/download/raw_pbp_{game['season']}/{provider_id(game)}.rds"


def scalar(value):
    if hasattr(value, 'size'):
        if value.size != 1:
            raise ValueError('Expected one provider value')
        return value.item()
    return value


def terminal_game(detail, scores):
    """Require explicit agreeing end-of-game play/drive and scoring evidence.

    Some nflverse files retain an INGAME summary after the complete play log.
    A low clock, kneel, lead or elapsed wall time is never sufficient.
    """
    from pandas import isna
    try:
        plays, drives, summaries = (detail[k] for k in ('plays','drives','scoringSummaries'))
        if any(frame.empty for frame in (plays,drives,summaries)):
            return False
        play, drive, summary = (frame.iloc[-1] for frame in (plays,drives,summaries))
        sequence = [scalar(v) for v in plays['orderSequence']]
        quarter = scalar(play['quarter'])
        if (any(type(v) is not int for v in sequence) or sequence != sorted(set(sequence))
                or type(quarter) is not int or quarter not in (4,5)
                or scalar(detail['period']) != quarter
                or play['playType'] != 'END_GAME' or play['playDescription'] != 'END GAME'
                or scalar(play['playDeleted']) is not False
                or scalar(detail.get('playReview')) is not False
                or (not isna(play.get('playReviewStatus')) and play.get('playReviewStatus') != '')
                or drive['endTransition'] != 'END_GAME'
                or scalar(drive['playIdEnded']) != scalar(play['playId'])
                or scalar(drive['playSeqEnded']) != sequence[-1]
                or scalar(drive['quarterEnd']) != quarter
                or drive['gameClockEnd'] != play['clockTime']
                or not re.fullmatch(r'0[0-9]:[0-5][0-9]',str(play['clockTime']))
                or (quarter == 4 and (play['clockTime'] != '00:00' or scores[0] == scores[1]))):
            return False
        recorded = [scalar(summary[k]) for k in ('homeScore','visitorScore')]
        return all(type(v) is int for v in recorded) and recorded == scores
    except (KeyError, IndexError, AttributeError, TypeError, ValueError):
        return False


def normalize_detail(detail, game, observed_at):
    """Match season/week filename, both teams and actual Eastern kickoff date."""
    provider_id(game)  # Validate season and identity BEFORE inspecting football values.
    if not game['kickoff']:
        raise ValueError('Cannot match a game without a confirmed kickoff')
    home = scalar(detail['homeTeam']['abbreviation'])
    away = scalar(detail['visitorTeam']['abbreviation'])
    if (ALIASES.get(home, home), ALIASES.get(away, away)) != (game['home'], game['away']):
        raise ValueError('Result teams do not match the archived matchup')
    start = datetime.strptime(scalar(detail['startTime']), '%m/%d/%y, %H:%M:%S').replace(tzinfo=EASTERN)
    kick = timestamp(game['kickoff'])
    # Exact season/week/teams filename plus the scheduled Eastern date identifies
    # the event. Allow a late actual start on that date (e.g. weather delay);
    # a different date or materially earlier start requires a confirmed schedule.
    if start.date() != kick.astimezone(EASTERN).date() or (start-kick).total_seconds() < -900:
        raise ValueError('Result kickoff does not match the archived matchup')
    phase = scalar(detail['phase'])
    if not isinstance(phase, str):
        raise ValueError('Missing explicit game phase')
    phase = phase.upper().strip()
    scores = [scalar(detail.get(key)) for key in ('homePointsTotal', 'visitorPointsTotal')]
    if any(value is not None and (type(value) is not int or not 0 <= value <= 200) for value in scores):
        raise ValueError('Invalid provider score')
    final = phase in FINAL_PHASES or (phase == 'INGAME' and terminal_game(detail, scores))
    normalized = {**{k:game[k] for k in ('id','season','week','home','away','kickoff','day')},
                  'phase':phase, 'validated':final,
                  'home_score':scores[0], 'away_score':scores[1]}
    state = status({**normalized, 'phase':'FINAL' if final else phase}, observed_at)
    if final and (state != 'completed' or start >= timestamp(observed_at)):
        raise ValueError('Final result lacks valid scores or follows an invalid time ordering')
    return {**normalized, 'status':state, 'provider_game_id':provider_id(game),
            'provider_event_id':str(scalar(detail['id'])), 'actual_start':iso(start)}


def normalize(raw, game, observed_at):
    provider_id(game)
    if len(raw) > MAX_RAW or not raw.startswith(b'\x1f\x8b'):
        raise ValueError('Unexpected or oversized result file')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        expanded = stream.read(MAX_EXPANDED+1)
    if len(expanded) > MAX_EXPANDED:
        raise ValueError('Expanded result file exceeds budget')
    import rdata
    parsed = rdata.conversion.convert(rdata.parser.parse_data(expanded, extension='.rds'))
    return normalize_detail(parsed['data']['viewer']['gameDetail'], game, observed_at)


def validate_observation(observation, raw, season, now):
    check_season(season)
    if (observation.get('schema_version') != 1 or observation.get('season') != season
            or observation.get('source_url') != source_url(observation['game'])
            or observation.get('license_url') != LICENSE or sha(raw) != observation.get('raw_sha256')
            or observation.get('provider_digest') != 'sha256:'+sha(raw)
            or not timestamp(observation['source_updated_at']) <= timestamp(observation['observed_at']) <= timestamp(now)):
        raise ValueError('Invalid result observation provenance')
    normalized = normalize(raw, observation['game'], observation['observed_at'])
    # Accept only the exact old interpretation of independently verified raw finals.
    # Original JSON, digest and observation time remain immutable, including
    # when a fresh runner restores an archive produced by the old parser.
    recovered = normalized['phase'] in {'FINAL_OVERTIME','INGAME'} and normalized['status'] == 'completed'
    legacy = {**normalized, 'validated':False, 'status':'unknown'} if recovered else normalized
    if observation['game'] not in (normalized, legacy):
        raise ValueError('Result observation does not reproduce from its raw source')
    if (normalized['status'] == 'completed'
            and timestamp(observation['source_updated_at']) <= timestamp(observation['game']['actual_start'])):
        raise ValueError('Final result publication must follow the actual start')
    return ValidatedObservation(observation, normalized)


def immutable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise ValueError('Immutable result evidence conflict')
    if not path.exists():
        path.write_bytes(body)


def load_observations(season, root=ROOT, now=None):
    check_season(season)
    directory = Path(root)/'data/results'/str(season)
    now = now or iso(datetime.now(timezone.utc))
    observations = []
    for path in sorted(directory.glob('observation-*.json')):
        body = path.read_bytes()
        if path.name != f'observation-{sha(body)}.json':
            raise ValueError('Result observation checksum mismatch')
        observation = json.loads(body)
        raw_path = directory/f"raw-{observation['raw_sha256']}.rds"
        observations.append(validate_observation(observation, raw_path.read_bytes(), season, now))
    return observations


def collect(games, season, *, root=ROOT, fetch=download, now=None):
    """One metadata request, only changed game files, no retries or live endpoint."""
    decision = now or datetime.now(timezone.utc)
    check_season(season)
    if season != current_season(decision) or any(g['season'] != season for g in games):
        raise ValueError('Result acquisition is current-season only')
    eligible = [g for g in games if g['kickoff'] and timestamp(g['kickoff']) < decision]
    if not eligible:
        return {'changed':False, 'captured':0, 'missing':[], 'requests':0}
    # A season contains at most 272 regular-season games. Only changed published
    # assets are downloaded; checking a missing asset does not make 272 requests.
    release_url = f'https://api.github.com/repos/nflverse/nflverse-pbp/releases/tags/raw_pbp_{season}'
    release = json.loads(fetch(release_url, maximum=2_000_000))
    if release.get('tag_name') != f'raw_pbp_{season}':
        raise ValueError('Unexpected result release season')
    assets = {a['name']:a for a in release['assets']}
    if len(assets) != len(release['assets']):
        raise ValueError('Duplicate provider assets')
    directory = Path(root)/'data/results'/str(season)
    previous = load_observations(season, root, iso(decision))
    known = {(o['game']['id'],o['game']['kickoff'],o['raw_sha256']) for o in previous}
    captured, missing, requests = 0, [], 1
    for game in sorted(eligible, key=lambda g:g['id']):
        name = provider_id(game)+'.rds'
        asset = assets.get(name)
        if asset is None:
            missing.append(game['id']); continue
        if (asset['browser_download_url'] != source_url(game) or asset.get('size', MAX_RAW+1) > MAX_RAW
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or '')):
            raise ValueError('Unexpected result asset URL, size or digest')
        if (game['id'],game['kickoff'],asset['digest'][7:]) in known:
            continue
        # Bound one run even when bootstrapping an unusually large archive.
        if captured >= 16:
            missing.append(game['id']); continue
        raw = fetch(source_url(game), maximum=MAX_RAW); requests += 1
        if asset['digest'] != 'sha256:'+sha(raw):
            raise ValueError('Result changed during fetch; no observation accepted')
        observed = now or datetime.now(timezone.utc)
        observation = {'schema_version':1, 'season':season, 'observed_at':iso(observed),
                       'source_updated_at':asset['updated_at'], 'source_url':source_url(game),
                       'license_url':LICENSE, 'raw_sha256':sha(raw), 'provider_digest':asset['digest'],
                       'game':normalize(raw, game, iso(observed))}
        validate_observation(observation,raw,season,iso(observed))
        immutable(directory/f'raw-{sha(raw)}.rds',raw)
        body = canonical(observation)
        immutable(directory/f'observation-{sha(body)}.json',body)
        captured += 1
    return {'changed':bool(captured), 'captured':captured, 'missing':missing, 'requests':requests}
