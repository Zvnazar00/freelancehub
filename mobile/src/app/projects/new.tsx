import { zodResolver } from '@hookform/resolvers/zod';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { applyServerFieldErrors } from '@/features/auth/formErrors';
import { useClients } from '@/features/clients/api';
import { useCreateProject } from '@/features/projects/api';
import { emptyProjectForm, PROJECT_COLORS, projectFormSchema, toProjectPayload, type ProjectFormValues } from '@/features/projects/schema';
import type { TxKey } from '@/shared/i18n';
import { AppText, Button, EmptyState, Icon, InlineError, Input, LoadingState, Screen, SegmentedControl } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export default function NewProjectScreen() {
  const { t } = useTranslation();
  const tr = (m?: string) => (m ? t(m as TxKey) : undefined);
  const params = useLocalSearchParams<{ clientId?: string }>();
  const clients = useClients();
  const create = useCreateProject();
  const [formError, setFormError] = useState<unknown>(null);
  const activeClients = (clients.data ?? []).filter((c) => c.archivedAt === null);

  const {
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues: emptyProjectForm(params.clientId ?? ''),
    mode: 'onTouched',
  });
  const billingType = useWatch({ control, name: 'billingType' });
  const clientId = useWatch({ control, name: 'clientId' });
  const currency = activeClients.find((c) => c.id === clientId)?.currency;

  const submit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      const project = await create.mutateAsync(toProjectPayload(values));
      router.replace({ pathname: '/projects/[id]', params: { id: project.id } });
    } catch (e) {
      const handled = applyServerFieldErrors(
        e,
        setError,
        { name: 'name', hourly_rate: 'hourlyRate', fixed_fee: 'fixedFee', budget_hours: 'budgetHours', client_id: 'clientId' },
        { NAME_TAKEN: { field: 'name', message: 'errors.NAME_TAKEN' } },
      );
      if (!handled) setFormError(e);
    }
  });

  if (clients.isPending) {
    return (
      <Screen edges={['bottom']}>
        <LoadingState rows={3} />
      </Screen>
    );
  }

  if (activeClients.length === 0) {
    return (
      <Screen edges={['bottom']} testID="new-project-screen">
        <EmptyState
          icon="people-outline"
          title={t('projectForm.noClients')}
          message={t('projects.needClient')}
          actionLabel={t('projectForm.addClient')}
          onAction={() => router.replace('/clients/new')}
        />
      </Screen>
    );
  }

  return (
    <Screen edges={['bottom']} contentStyle={styles.content} testID="new-project-screen" keyboard>
      <View style={styles.block}>
        <AppText variant="captionMedium" color="textSecondary">
          {t('projectForm.client')}
        </AppText>
        <Controller
          control={control}
          name="clientId"
          render={({ field }) => (
            <View style={styles.chips} accessibilityRole="radiogroup" accessibilityLabel={t('projectForm.clientA11y')}>
              {activeClients.map((c) => {
                const selected = field.value === c.id;
                return (
                  <Pressable
                    key={c.id}
                    testID={`project-client-${c.id}`}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: selected }}
                    onPress={() => field.onChange(c.id)}
                    style={[styles.chip, selected && styles.chipActive]}
                  >
                    <AppText variant="captionMedium" color={selected ? 'accentText' : 'textSecondary'}>
                      {c.name}
                    </AppText>
                  </Pressable>
                );
              })}
            </View>
          )}
        />
        {errors.clientId ? (
          <AppText variant="caption" color="danger">
            {tr(errors.clientId.message)}
          </AppText>
        ) : null}
      </View>

      <Controller
        control={control}
        name="name"
        render={({ field }) => (
          <Input
            testID="project-name"
            label={t('projectForm.name')}
            placeholder={t('projectForm.namePlaceholder')}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.name?.message)}
          />
        )}
      />

      <View style={styles.block}>
        <AppText variant="captionMedium" color="textSecondary">
          {t('projectForm.billing')}
        </AppText>
        <Controller
          control={control}
          name="billingType"
          render={({ field }) => (
            <SegmentedControl
              accessibilityLabel={t('projectForm.billingA11y')}
              value={field.value}
              onChange={field.onChange}
              options={[
                { value: 'hourly', label: t('projectForm.hourly') },
                { value: 'fixed', label: t('projectForm.fixed') },
                { value: 'non_billable', label: t('projectForm.nonBillable') },
              ]}
            />
          )}
        />
      </View>

      {billingType === 'hourly' ? (
        <Controller
          control={control}
          name="hourlyRate"
          render={({ field }) => (
            <Input
              testID="project-rate"
              label={`${t('projectForm.rate')}${currency ? ` · ${currency}` : ''}`}
              placeholder="85.00"
              keyboardType="decimal-pad"
              mono
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.hourlyRate?.message)}
              helper={t('projectForm.rateHelper')}
            />
          )}
        />
      ) : null}
      {billingType === 'fixed' ? (
        <Controller
          control={control}
          name="fixedFee"
          render={({ field }) => (
            <Input
              testID="project-fee"
              label={`${t('projectForm.fee')}${currency ? ` · ${currency}` : ''}`}
              placeholder="2500.00"
              keyboardType="decimal-pad"
              mono
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.fixedFee?.message)}
            />
          )}
        />
      ) : null}

      <Controller
        control={control}
        name="budgetHours"
        render={({ field }) => (
          <Input
            label={t('projectForm.budget')}
            placeholder="40"
            keyboardType="decimal-pad"
            mono
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.budgetHours?.message)}
          />
        )}
      />

      <View style={styles.block}>
        <AppText variant="captionMedium" color="textSecondary">
          {t('projectForm.color')}
        </AppText>
        <Controller
          control={control}
          name="color"
          render={({ field }) => (
            <View style={styles.colors}>
              {PROJECT_COLORS.map((c) => {
                const selected = field.value.toUpperCase() === c.toUpperCase();
                return (
                  <Pressable
                    key={c}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: selected }}
                    accessibilityLabel={t('projectForm.colorA11y', { color: c })}
                    onPress={() => field.onChange(c)}
                    style={[styles.swatch, { backgroundColor: c }, selected && styles.swatchActive]}
                  >
                    {selected ? <Icon name="checkmark" size={18} color="textOnAccent" /> : null}
                  </Pressable>
                );
              })}
            </View>
          )}
        />
      </View>

      <InlineError error={formError} />
      <Button testID="project-submit" label={t('projectForm.submit')} size="lg" fullWidth loading={isSubmitting} onPress={() => void submit()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: spacing.lg, gap: spacing.lg },
  block: { gap: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    minHeight: 40,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface2,
  },
  chipActive: { borderColor: colors.accentBorder, backgroundColor: colors.accentSoft },
  colors: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  swatch: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  swatchActive: { borderWidth: 3, borderColor: colors.textPrimary },
});
