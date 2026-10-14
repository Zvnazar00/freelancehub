import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';

import { isApiError } from '@/shared/api/errors';

/**
 * Puts server-side validation errors next to the matching field. Returns true when at least one
 * field error was applied (the generic banner can then be skipped).
 * `fields` maps API field names (snake_case) to form field names.
 */
export function applyServerFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: Record<string, Path<T>>,
  codeToField: Record<string, { field: Path<T>; message: string }> = {},
): boolean {
  if (!isApiError(error)) return false;
  const byCode = codeToField[error.code];
  if (byCode) {
    setError(byCode.field, { type: 'server', message: byCode.message });
    return true;
  }
  let applied = false;
  for (const fe of error.fieldErrors) {
    const field = fields[fe.field];
    if (field) {
      setError(field, { type: 'server', message: fe.message });
      applied = true;
    }
  }
  return applied;
}
