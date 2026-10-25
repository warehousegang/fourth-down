import {render,screen,fireEvent} from '@testing-library/react';
import {expect,it} from 'vitest';
import {operationsFixture,completedFixture} from './intelligence-fixtures';
import {PredictionScoreboard,predictionPerformance} from './PredictionScoreboard';

it('shows an honest zero sample and excludes historical validation',()=>{
  const ops=operationsFixture();const stats=predictionPerformance(ops,7);
  expect(stats.count).toBe(0);expect(stats.accuracy).toBeNull();expect(stats.brier).toBeNull();
  expect(stats.pending).toBe(13);
  render(<PredictionScoreboard operations={ops} week={7}/>);
  expect(screen.getByText(/No games scored yet/)).toBeInTheDocument();
  expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
});
it.each([[24,17,0],[17,24,1]] as const)('uses the designated real evaluation for %i-%i', (home,away,correct)=>{
  const ops=completedFixture(home,away);const stats=predictionPerformance(ops,7);
  expect(stats.count).toBe(1);expect(stats.correct).toBe(correct);expect(stats.incorrect).toBe(1-correct);
  expect(stats.accuracy).toBe(correct);expect(stats.brier).toBe(ops.metrics.primary.brier);
  expect(stats.logLoss).toBe(ops.metrics.primary.log_loss);expect(stats.lastVerified).toBe(ops.games[0].result!.observed_at);
});
it('keeps weekly and season counts separate for partial results',()=>{
  const ops=completedFixture();
  const pending=structuredClone(ops.games[0]);pending.id='ngs-2026-90000';pending.week=8;pending.status='scheduled';pending.result=null;pending.evaluations=[];pending.final_forecast_id=null;
  ops.games.push(pending);ops.catalog.push({...ops.catalog.find(f=>f.eligible)!,game_id:pending.id,week:8});
  expect(predictionPerformance(ops,7).count).toBe(1);expect(predictionPerformance(ops,8).count).toBe(0);
  expect(predictionPerformance(ops).pending).toBe(1);
  render(<PredictionScoreboard operations={ops} week={7}/>);
  fireEvent.click(screen.getByRole('button',{name:'Season to date'}));
  expect(screen.getByText('2026 to date — Prediction Performance')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Season to date'})).toHaveAttribute('aria-pressed','true');
});
it('ties and canceled games never enter accuracy or pending totals',()=>{
  const ops=completedFixture(24,24);expect(predictionPerformance(ops).count).toBe(0);
  expect(predictionPerformance(ops).excluded).toBe(1);
  ops.games[0].status='canceled';ops.games[0].result=null;
  expect(predictionPerformance(ops).count).toBe(0);expect(predictionPerformance(ops).excluded).toBe(1);
});

it('distinguishes the browser check from provider publication and verified result observation',()=>{
  const ops=completedFixture();
  ops.result_feed={provider:'nflverse',source_url:'https://github.com/nflverse/nflverse-pbp',license_url:'https://github.com/nflverse/nflverse-pbp/blob/master/LICENSE.md',base_operations_sha256:'a'.repeat(64),last_observed_at:ops.generated_at,source_updated_at:'2026-10-25T16:46:11Z'};
  const {container}=render(<PredictionScoreboard operations={ops} week={7} checkedAt="2026-10-25T17:01:00Z"/>);
  expect(screen.getByText('Results last checked')).toBeInTheDocument();
  expect(screen.getByText('Result provider last published')).toBeInTheDocument();
  expect(container.querySelector('time[datetime="2026-10-25T17:01:00Z"]')).toBeInTheDocument();
  expect(container.querySelector('time[datetime="2026-10-25T16:46:11Z"]')).toBeInTheDocument();
  expect(screen.getByText(/check time confirms a successful dashboard fetch/)).toBeInTheDocument();
});
