import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { StyleSheet } from 'react-native';

import { useCurrentUser } from '@/features/auth/store';
import { useCreateClient } from '@/features/clients/api';
import { ClientForm } from '@/features/clients/components/ClientForm';
import { emptyClientForm, toClientPayload } from '@/features/clients/schema';
import { InlineError, Screen } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export default function NewClientScreen() {
  const user = useCurrentUser();
  const create = useCreateClient();
  const [error, setError] = useState<unknown>(null);
  const defaultValues = useMemo(() => ({ ...emptyClientForm, currency: user.defaultCurrency }), [user.defaultCurrency]);
  return (
    <Screen edges={['bottom']} contentStyle={styles.content} testID="new-client-screen" keyboard>
      <InlineError error={error} testID="client-error" />
      <ClientForm
        defaultValues={defaultValues}
        onSubmit={async (values, setFieldError) => {
          setError(null);
          try {
            const client = await create.mutateAsync(toClientPayload(values));
            router.replace({ pathname: '/clients/[id]', params: { id: client.id } });
          } catch (e) {
            if (!setFieldError(e)) setError(e);
          }
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: spacing.lg, gap: spacing.lg },
});
