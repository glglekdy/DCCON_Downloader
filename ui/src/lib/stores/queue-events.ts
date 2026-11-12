import { onEvent } from '../api'
import { dockHidden, type Queue } from './queue'

/** 백엔드 queue-* 이벤트를 큐에 연결한다. 돌려주는 함수가 모두 해제한다. */
export function wireQueueEvents(q: Queue): () => void {
  const pending = [
    onEvent<Parameters<Queue['onStarted']>[0]>('queue-started', (p) => {
      q.onStarted(p)
      dockHidden.set(false)
    }),
    onEvent<Parameters<Queue['onProgress']>[0]>('queue-progress', (p) => q.onProgress(p)),
    onEvent<Parameters<Queue['onPackageDone']>[0]>('queue-package-done', (p) =>
      q.onPackageDone(p),
    ),
    onEvent<Parameters<Queue['onError']>[0]>('queue-error', (p) => q.onError(p)),
    onEvent<Parameters<Queue['onFinished']>[0]>('queue-finished', (p) => q.onFinished(p)),
  ]
  return () => {
    for (const p of pending) void p.then((unlisten) => unlisten()).catch(() => undefined)
  }
}
