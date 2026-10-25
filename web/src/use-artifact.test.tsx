import {act,renderHook} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {useArtifact} from './use-artifact';
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()});
it('polls visible data without clearing saved evidence on outage, then accepts a correction',async()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T17:00:00Z'));
  const load=vi.fn().mockResolvedValueOnce({score:24}).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({score:27});
  const {result,unmount}=renderHook(()=>useArtifact(load,60_000));
  await act(async()=>{});expect(result.current.data).toEqual({score:24});
  expect(result.current.checkedAt).toBe("2026-10-25T17:00:00.000Z");
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000)});
  expect(result.current.data).toEqual({score:24});expect(result.current.error).toBe('offline');
  expect(result.current.checkedAt).toBe("2026-10-25T17:00:00.000Z");
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000)});
  expect(result.current.data).toEqual({score:27});expect(result.current.error).toBe('');
  expect(result.current.checkedAt).toBe("2026-10-25T17:02:00.000Z");
  unmount();await vi.advanceTimersByTimeAsync(60_000);expect(load).toHaveBeenCalledTimes(3);
});
it('avoids overlapping requests and pauses hidden-tab polling',async()=>{
  vi.useFakeTimers();let resolve!:(value:number)=>void;
  const load=vi.fn(()=>new Promise<number>(r=>{resolve=r}));
  const {result,unmount}=renderHook(()=>useArtifact(load,60_000));
  await act(async()=>{await vi.advanceTimersByTimeAsync(120_000)});
  expect(load).toHaveBeenCalledTimes(1);
  await act(async()=>{resolve(1)});expect(result.current.data).toBe(1);
  vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');
  await act(async()=>{await vi.advanceTimersByTimeAsync(120_000)});
  expect(load).toHaveBeenCalledTimes(1);unmount();
});

it('advances the successful published-results check even when the artifact is unchanged',async()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T17:00:00Z'));
  const data={score:16},load=vi.fn().mockResolvedValue(data);
  const {result,unmount}=renderHook(()=>useArtifact(load,60_000));
  await act(async()=>{});expect(result.current.checkedAt).toBe('2026-10-25T17:00:00.000Z');
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000)});
  expect(result.current.data).toBe(data);expect(result.current.checkedAt).toBe('2026-10-25T17:01:00.000Z');
  unmount();
});
