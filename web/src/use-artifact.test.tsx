import {act,renderHook} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {useArtifact} from './use-artifact';
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()});
it('polls visible data without clearing saved evidence on outage, then accepts a correction',async()=>{
  vi.useFakeTimers();
  const load=vi.fn().mockResolvedValueOnce({score:24}).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({score:27});
  const {result,unmount}=renderHook(()=>useArtifact(load,60_000));
  await act(async()=>{});expect(result.current.data).toEqual({score:24});
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000)});
  expect(result.current.data).toEqual({score:24});expect(result.current.error).toBe('offline');
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000)});
  expect(result.current.data).toEqual({score:27});expect(result.current.error).toBe('');
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
