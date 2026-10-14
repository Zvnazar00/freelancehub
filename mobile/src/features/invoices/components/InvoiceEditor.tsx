import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { errorMessageKey, isApiError } from '@/shared/api';
import type { TxKey } from '@/shared/i18n';
import { centsToDecimal, decimalToCents, formatMoney } from '@/shared/lib/money';
import { formatCalendarDate, formatDuration, localDateKey } from '@/shared/lib/time';
import type { CurrencyCode, Invoice } from '@/shared/types/domain';
import {
  AppText,
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorState,
  IconButton,
  InlineError,
  Input,
  LoadingState,
  Screen,
  SectionHeader,
  SegmentedControl,
} from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

import { newIdempotencyKey, useBillableEntries, useCreateInvoice, useUpdateInvoice, type NewInvoice } from '../api';
import { draftEntryIds, draftPreview, entryCurrencies, extraLinesFrom, isExtraLineValid, type ExtraLine } from '../draft';
import { daysBetween, duePresetsWith, dueDateFor, invoiceFormSchema, isIsoDate, normalizeTaxRate, taxRateInput } from '../schema';
import { EntryPicker } from './EntryPicker';

export interface EditorClient {
  id: string;
  name: string;
  currency: CurrencyCode;
}

type Mode =
  | { kind: 'create'; onChangeClient: () => void }
  /** Editing a draft: its entries start selected, its currency is fixed, the PATCH carries its version. */
  | { kind: 'edit'; invoice: Invoice; onReload: () => void };

/**
 * The invoice form, shared by "New invoice" and "Edit draft". The preview uses the server's rounding rules
 * (integer cents); what the server stores is what the detail screen shows afterwards.
 */
export function InvoiceEditor({ client, mode }: { client: EditorClient; mode: Mode }) {
  const { t } = useTranslation();
  const tr = (m?: string) => (m ? t(m as TxKey) : undefined);
  const draft = mode.kind === 'edit' ? mode.invoice : null;
  const billable = useBillableEntries(client.id, draft?.id);
  const create = useCreateInvoice();
  const update = useUpdateInvoice(draft?.id ?? '');
  const mutation = draft ? update : create;
  const [key] = useState(newIdempotencyKey);
  const today = useMemo(() => new Date(), []);
  const onDraft = useMemo(() => (draft ? draftEntryIds(draft.items) : new Set<string>()), [draft]);

  // New invoice: every entry starts selected. Draft: exactly the entries already on it.
  // `picked` only stores what the user changed, so entries that load later still get the right default.
  const [picked, setPicked] = useState<ReadonlyMap<string, boolean>>(new Map());
  const [pickedCurrency, setCurrency] = useState<CurrencyCode | null>(null);
  const [issueDate, setIssueDate] = useState(draft?.issueDate ?? localDateKey(today));
  const [dueDays, setDueDays] = useState<number>(draft ? daysBetween(draft.issueDate, draft.dueDate) : 14);
  const [taxRate, setTaxRate] = useState(draft ? taxRateInput(draft.taxRate) : '');
  const [notes, setNotes] = useState(draft?.notes ?? '');
  const [extras, setExtras] = useState<ExtraLine[]>(() => (draft ? extraLinesFrom(draft.items, newIdempotencyKey) : []));
  const [submitted, setSubmitted] = useState(false);
  const presets = useMemo(() => duePresetsWith(dueDays), [dueDays]);

  const allEntries = billable.data?.entries ?? [];
  const currencies = draft ? [draft.currency] : entryCurrencies(allEntries, client.currency);
  const currency = pickedCurrency && currencies.includes(pickedCurrency) ? pickedCurrency : (currencies[0] ?? client.currency);
  const entries = allEntries.filter((e) => e.currency === currency);
  const isSelected = (id: string) => picked.get(id) ?? (draft ? onDraft.has(id) : true);
  const selected = new Set(entries.filter((e) => isSelected(e.id)).map((e) => e.id));
  const preview = draftPreview(entries, selected, extras, taxRate);

  const parsed = invoiceFormSchema.safeParse({ issueDate, dueDays, taxRate, notes });
  const fieldError = (name: 'issueDate' | 'taxRate' | 'notes') =>
    submitted || name !== 'issueDate' ? tr(parsed.error?.issues.find((i) => i.path[0] === name)?.message) : undefined;
  const extrasValid = extras.every(isExtraLineValid);
  const hasLines = selected.size > 0 || extras.length > 0;
  const canSubmit = parsed.success && extrasValid && hasLines && decimalToCents(preview.total) > 0 && !billable.isPending;
  const conflict = isApiError(mutation.error) && mutation.error.code === 'VERSION_CONFLICT';

  const toggle = (id: string) => setPicked((prev) => new Map(prev).set(id, !isSelected(id)));
  const setAll = (value: boolean) => setPicked(new Map(entries.map((e) => [e.id, value])));

  const submit = () => {
    setSubmitted(true);
    if (!canSubmit || !parsed.success) return;
    const payload: Omit<NewInvoice, 'clientId'> = {
      timeEntryIds: entries.filter((e) => selected.has(e.id)).map((e) => e.id),
      issueDate,
      dueDate: dueDateFor(issueDate, dueDays),
      taxRate: normalizeTaxRate(taxRate),
      notes: notes.trim(),
      items: extras.map((x) => ({ description: x.description.trim(), unitPrice: centsToDecimal(decimalToCents(x.amount)) })),
    };
    if (draft) {
      update.mutate(
        { ...payload, version: draft.version },
        {
          // Back to the detail screen it was opened from; a deep link without history lands on the detail too.
          onSuccess: (invoice) =>
            router.canGoBack() ? router.back() : router.replace({ pathname: '/invoices/[id]', params: { id: invoice.id } }),
        },
      );
    } else {
      create.mutate(
        { ...payload, clientId: client.id, idempotencyKey: key },
        { onSuccess: (invoice) => router.replace({ pathname: '/invoices/[id]', params: { id: invoice.id } }) },
      );
    }
  };

  return (
    <Screen edges={['bottom']} keyboard testID={draft ? 'invoice-edit-screen' : 'invoice-new-screen'} contentStyle={styles.content}>
      <Card padding="md">
        <View style={styles.clientRow}>
          <Avatar name={client.name} size={40} />
          <View style={styles.flex}>
            <AppText variant="overline" color="textMuted">
              {t('invoiceForm.billTo')}
            </AppText>
            <AppText variant="bodyMedium" numberOfLines={1}>
              {client.name}
            </AppText>
          </View>
          {mode.kind === 'create' ? <Button label={t('invoiceForm.change')} size="sm" variant="ghost" onPress={mode.onChangeClient} /> : null}
        </View>
        {draft ? (
          <AppText variant="caption" color="textMuted" style={styles.note}>
            {t('invoiceForm.editHint')}
          </AppText>
        ) : null}
      </Card>

      <View style={styles.section}>
        <SectionHeader
          title={t('invoiceForm.entries')}
          meta={entries.length ? t('invoiceForm.selectedCount', { selected: selected.size, total: entries.length }) : undefined}
          actionLabel={entries.length ? (selected.size === entries.length ? t('invoiceForm.selectNone') : t('invoiceForm.selectAll')) : undefined}
          onAction={() => setAll(selected.size !== entries.length)}
        />
        {currencies.length > 1 ? (
          <SegmentedControl
            accessibilityLabel={t('invoiceForm.currencyA11y')}
            value={currency}
            onChange={(c) => {
              setCurrency(c);
              setPicked(new Map());
            }}
            options={currencies.map((c) => ({ value: c, label: c }))}
          />
        ) : null}
        <Card padding="md" style={styles.listCard}>
          {billable.isPending ? (
            <LoadingState rows={3} />
          ) : billable.isError && !billable.data ? (
            <ErrorState message={t(errorMessageKey(billable.error, 'invoice'))} onRetry={() => void billable.refetch()} retrying={billable.isFetching} />
          ) : entries.length === 0 ? (
            <EmptyState compact icon="time-outline" title={t('invoiceForm.noEntries')} message={t('invoiceForm.noEntriesHint')} />
          ) : (
            <EntryPicker entries={entries} selected={selected} onToggle={toggle} />
          )}
        </Card>
        {billable.data?.truncated ? (
          <AppText variant="caption" color="warning">
            {t('invoiceForm.truncated')}
          </AppText>
        ) : null}
      </View>

      <View style={styles.section}>
        <SectionHeader
          title={t('invoiceForm.extraLines')}
          actionLabel={extras.length < 20 ? t('invoiceForm.addLine') : undefined}
          onAction={() => setExtras((x) => [...x, { key: newIdempotencyKey(), description: '', amount: '' }])}
        />
        {extras.length === 0 ? (
          <AppText variant="caption" color="textMuted">
            {t('invoiceForm.extraLinesHint')}
          </AppText>
        ) : (
          extras.map((line, i) => {
            const change = (patch: Partial<ExtraLine>) => setExtras((all) => all.map((x) => (x.key === line.key ? { ...x, ...patch } : x)));
            const invalidAmount = submitted && !isExtraLineValid(line);
            return (
              <Card key={line.key} padding="md" style={styles.extra}>
                <View style={styles.extraRow}>
                  <View style={styles.flex}>
                    <Input
                      testID={`extra-description-${i}`}
                      label={t('invoiceForm.lineDescription')}
                      placeholder={t('invoiceForm.lineDescriptionPlaceholder')}
                      value={line.description}
                      onChangeText={(description) => change({ description })}
                      maxLength={500}
                    />
                  </View>
                  <IconButton
                    testID={`extra-remove-${i}`}
                    icon="trash-outline"
                    variant="plain"
                    color="danger"
                    accessibilityLabel={t('invoiceForm.removeLine')}
                    onPress={() => setExtras((all) => all.filter((x) => x.key !== line.key))}
                  />
                </View>
                <Input
                  testID={`extra-amount-${i}`}
                  label={t('invoiceForm.lineAmount', { currency })}
                  placeholder="250.00"
                  keyboardType="decimal-pad"
                  mono
                  value={line.amount}
                  onChangeText={(amount) => change({ amount })}
                  error={invalidAmount ? t('invoiceForm.errors.lineInvalid') : undefined}
                />
              </Card>
            );
          })
        )}
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('invoiceForm.details')} />
        <Input
          testID="invoice-issue-date"
          label={t('invoiceForm.issueDate')}
          placeholder="YYYY-MM-DD"
          mono
          autoCapitalize="none"
          value={issueDate}
          onChangeText={setIssueDate}
          error={fieldError('issueDate')}
        />
        <View style={styles.gapSm}>
          <AppText variant="captionMedium" color="textSecondary">
            {t('invoiceForm.dueIn')}
          </AppText>
          <SegmentedControl
            accessibilityLabel={t('invoiceForm.dueIn')}
            value={String(dueDays)}
            onChange={(v) => setDueDays(Number(v))}
            options={presets.map((d) => ({ value: String(d), label: t('invoiceForm.days', { count: d }) }))}
          />
          {isIsoDate(issueDate) ? (
            <AppText variant="caption" color="textMuted" testID="invoice-due-on">
              {t('invoiceForm.dueOn', { date: formatCalendarDate(dueDateFor(issueDate, dueDays)) })}
            </AppText>
          ) : null}
        </View>
        <Input
          testID="invoice-tax"
          label={t('invoiceForm.taxRate')}
          placeholder="0"
          keyboardType="decimal-pad"
          mono
          value={taxRate}
          onChangeText={setTaxRate}
          error={fieldError('taxRate')}
          helper={t('invoiceForm.taxHelper')}
        />
        <Input
          testID="invoice-notes"
          label={t('invoiceForm.notes')}
          placeholder={t('invoiceForm.notesPlaceholder')}
          value={notes}
          onChangeText={setNotes}
          error={fieldError('notes')}
          multiline
          maxLength={2000}
        />
      </View>

      <Card variant="raised" style={styles.totals} testID="invoice-preview">
        <TotalRow label={t('invoiceForm.time', { count: preview.count })} value={formatDuration(preview.seconds)} />
        <TotalRow label={t('invoices.subtotal')} value={formatMoney(preview.subtotal, currency)} />
        {preview.tax !== '0.00' ? <TotalRow label={t('invoices.tax', { rate: taxRate })} value={formatMoney(preview.tax, currency)} /> : null}
        <View style={styles.rule} />
        <TotalRow label={t('invoices.total')} value={formatMoney(preview.total, currency)} strong testID="invoice-preview-total" />
        <AppText variant="caption" color="textMuted">
          {t('invoiceForm.previewNote')}
        </AppText>
      </Card>

      {submitted && !hasLines ? (
        <AppText variant="caption" color="danger">
          {t('invoiceForm.errors.noLines')}
        </AppText>
      ) : null}
      {conflict && mode.kind === 'edit' ? (
        <Card padding="md" style={styles.conflict} testID="invoice-conflict">
          <AppText variant="captionMedium" color="warning">
            {t('invoiceForm.conflict')}
          </AppText>
          <Button label={t('invoiceForm.reload')} size="sm" variant="secondary" icon="refresh" onPress={mode.onReload} testID="invoice-reload" />
        </Card>
      ) : (
        <InlineError error={mutation.error} scope="invoice" />
      )}
      <Button
        testID={draft ? 'invoice-save' : 'invoice-create'}
        label={draft ? t('invoiceForm.save') : t('invoiceForm.submit')}
        icon={draft ? 'checkmark' : 'document-text-outline'}
        size="lg"
        fullWidth
        loading={mutation.isPending}
        onPress={submit}
      />
    </Screen>
  );
}

function TotalRow({ label, value, strong = false, testID }: { label: string; value: string; strong?: boolean; testID?: string }) {
  return (
    <View style={styles.totalRow}>
      <AppText variant={strong ? 'subheading' : 'caption'} color={strong ? 'textPrimary' : 'textSecondary'}>
        {label}
      </AppText>
      <AppText variant={strong ? 'monoLarge' : 'mono'} testID={testID}>
        {value}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl },
  flex: { flex: 1 },
  clientRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  note: { marginTop: spacing.sm },
  section: { gap: spacing.md },
  gapSm: { gap: spacing.sm },
  listCard: { paddingVertical: spacing.xs },
  extra: { gap: spacing.md },
  extraRow: { flexDirection: 'row', alignItems: 'flex-end', gap: spacing.sm },
  totals: { gap: spacing.sm },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rule: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  conflict: { gap: spacing.sm, borderColor: colors.warning, borderWidth: 1 },
});
