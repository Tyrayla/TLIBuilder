import type { UploadOutcome } from './cloudSync'

export type SaveDestination = 'local-only' | 'local-and-cloud'

export interface SaveAndSyncResult<T> {
  saved: T
  upload: UploadOutcome | null
}

/** Close the save dialog after local saves and successful or already-synced uploads. */
export function shouldDismissSaveDialog(destination: SaveDestination, upload: UploadOutcome | null): boolean {
  return destination === 'local-only' || upload === null || upload.kind === 'uploaded' || upload.kind === 'unchanged'
}

/** Save to the local library first, then make an optional explicit cloud upload. */
export async function saveLocalThenMaybeUpload<T extends { id?: string }>(
  saveLocal: () => Promise<T>,
  destination: SaveDestination,
  upload: (localBuildId: string) => Promise<UploadOutcome>,
): Promise<SaveAndSyncResult<T>> {
  const saved = await saveLocal()
  if (destination !== 'local-and-cloud' || !saved.id) return { saved, upload: null }

  try {
    return { saved, upload: await upload(saved.id) }
  } catch (error) {
    return {
      saved,
      upload: {
        kind: 'error',
        code: 'unexpected',
        message: error instanceof Error ? error.message : 'The cloud upload failed.',
      },
    }
  }
}
