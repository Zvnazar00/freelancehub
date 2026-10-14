import type { SharedFile } from './files';

export type { SharedFile } from './files';

export function safeFilename(name: string): string {
  return name.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120) || 'export';
}

/** Web: hand the bytes to the browser as a regular download (the Web Share API cannot share local files). */
export async function saveAndShare({ bytes, filename, mimeType }: SharedFile): Promise<'shared' | 'saved'> {
  const url = URL.createObjectURL(new Blob([bytes], { type: mimeType }));
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = safeFilename(filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  return 'saved';
}
