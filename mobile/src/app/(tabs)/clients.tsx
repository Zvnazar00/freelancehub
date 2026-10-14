import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useClients } from '@/features/clients/api';
import { ClientCard } from '@/features/clients/components/ClientCard';
import { errorMessageKey } from '@/shared/api';
import { EmptyState, ErrorState, IconButton, Input, LoadingState, OfflineBanner, ScreenHeader } from '@/shared/ui';
import { colors, layout, spacing } from '@/shared/theme';

export default function ClientsScreen() {
  const { t } = useTranslation();
  const clientsQuery = useClients();
  const [query, setQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const clients = useMemo(() => clientsQuery.data ?? [], [clientsQuery.data]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return clients
      .filter((c) => c.archivedAt === null)
      .filter((c) => !q || c.name.toLowerCase().includes(q) || (c.company ?? '').toLowerCase().includes(q));
  }, [clients, query]);

  const refresh = () => {
    setRefreshing(true);
    void clientsQuery.refetch().finally(() => setRefreshing(false));
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="clients-screen">
      <FlatList
        data={rows}
        keyExtractor={(c) => c.id}
        refreshing={refreshing}
        onRefresh={refresh}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
        ListHeaderComponent={
          <View style={styles.header}>
            <ScreenHeader
              subtitle={t('clients.total', { count: clients.length })}
              title={t('clients.title')}
              right={<IconButton testID="add-client" icon="add" variant="accent" accessibilityLabel={t('clients.add')} onPress={() => router.push('/clients/new')} />}
            />
            <OfflineBanner />
            <Input
              placeholder={t('clients.searchPlaceholder')}
              leftIcon="search"
              value={query}
              onChangeText={setQuery}
              autoCorrect={false}
              accessibilityLabel={t('clients.searchA11y')}
              right={query ? <IconButton icon="close" variant="plain" size={16} accessibilityLabel={t('common.clearSearch')} onPress={() => setQuery('')} /> : null}
            />
          </View>
        }
        ListEmptyComponent={
          clientsQuery.isPending ? (
            <LoadingState rows={3} />
          ) : clientsQuery.isError ? (
            <ErrorState message={t(errorMessageKey(clientsQuery.error))} onRetry={() => void clientsQuery.refetch()} retrying={clientsQuery.isFetching} />
          ) : query ? (
            <EmptyState
              icon="search"
              title={t('clients.emptySearch')}
              message={t('clients.emptySearchHint', { query: query.trim() })}
              actionLabel={t('common.clearSearch')}
              onAction={() => setQuery('')} />
          ) : (
            <EmptyState
              icon="people-outline"
              title={t('clients.empty')}
              message={t('clients.emptyHint')}
              actionLabel={t('clients.add')}
              onAction={() => router.push('/clients/new')} />
          )
        }
        renderItem={({ item }) => (
          <ClientCard client={item} onPress={() => router.push({ pathname: '/clients/[id]', params: { id: item.id } })} />
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: {
    width: '100%',
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingTop: spacing.md,
    paddingBottom: spacing.huge,
  },
  header: { gap: spacing.lg, marginBottom: spacing.lg },
  sep: { height: spacing.md },
});
