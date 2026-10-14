import { useMutation } from '@tanstack/react-query';

import { downloadFile } from '@/shared/api';
import { saveAndShare } from '@/shared/lib/files';

export type ExportKind = 'time-entries' | 'invoices';

export interface ExportRequest {
  kind: ExportKind;
  from: string;
  to: string;
  clientId?: string;
  projectId?: string;
}

/** Downloads a CSV for the range (server-rendered, time zone aware) and opens the share sheet / browser download. */
export async function exportCsv({ kind, from, to, clientId, projectId }: ExportRequest) {
  const file = await downloadFile(
    `/exports/${kind}.csv`,
    { from, to, client_id: clientId, project_id: projectId },
    `${kind}_${from}_${to}.csv`,
  );
  return saveAndShare({ ...file, mimeType: 'text/csv', uti: 'public.comma-separated-values-text' });
}

export function useExportCsv() {
  return useMutation({ mutationFn: exportCsv });
}
