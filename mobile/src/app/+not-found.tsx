import { router, Stack } from 'expo-router';
import { useTranslation } from 'react-i18next';

import { EmptyState, Screen } from '@/shared/ui';

export default function NotFoundScreen() {
  const { t } = useTranslation();
  return (
    <Screen edges={['bottom']}>
      <Stack.Screen options={{ title: t('screens.notFound') }} />
      <EmptyState icon="compass-outline" title={t('notFound.title')} message={t('notFound.hint')} actionLabel={t('notFound.home')} onAction={() => router.replace('/')} />
    </Screen>
  );
}
