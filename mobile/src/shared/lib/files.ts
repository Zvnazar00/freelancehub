import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';

export interface SharedFile {
  bytes: ArrayBuffer;
  filename: string;
  mimeType: string;
  /** iOS Uniform Type Identifier, e.g. "com.adobe.pdf". */
  uti?: string;
}

/** A file name that is safe on every platform (the server already sends plain ASCII names). */
export function safeFilename(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120) || 'export';
}

/**
 * Writes the bytes to the app cache and opens the system share sheet (Save to Files, Mail, Drive…).
 * The cache copy is overwritten on the next export of the same name and cleaned up by the OS.
 */
export async function saveAndShare({ bytes, filename, mimeType, uti }: SharedFile): Promise<'shared' | 'saved'> {
  const file = new File(Paths.cache, safeFilename(filename));
  file.create({ overwrite: true, intermediates: true });
  file.write(new Uint8Array(bytes));
  if (!(await Sharing.isAvailableAsync())) return 'saved';
  await Sharing.shareAsync(file.uri, { mimeType, UTI: uti, dialogTitle: filename });
  return 'shared';
}
