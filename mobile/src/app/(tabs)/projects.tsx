import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useProjects } from '@/features/projects/api';
import { ProjectCard } from '@/features/projects/components/ProjectCard';
import { useTimerQuery } from '@/features/timer/api';
import type { ProjectStatus } from '@/shared/types/domain';
import { EmptyState, ErrorState, IconButton, Input, LoadingState, OfflineBanner, ScreenHeader, SegmentedControl } from '@/shared/ui';
import { colors, layout, spacing } from '@/shared/theme';

type Filter = ProjectStatus | 'all';

export default function ProjectsScreen() {
  const { t } = useTranslation();
  const query = useProjects();
  const timer = useTimerQuery();
  const [filter, setFilter] = useState<Filter>('active');
  const [search, setSearch] = useState('');

  const [refreshing, setRefreshing] = useState(false);
  const projects = useMemo(() => query.data ?? [], [query.data]);
  const trackingProjectId = timer.data?.entry?.projectId ?? null;

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: projects.length, active: 0, on_hold: 0, completed: 0 };
    for (const p of projects) c[p.status]++;
    return c;
  }, [projects]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return projects
      .filter((p) => filter === 'all' || p.status === filter)
      .filter((p) => !q || p.name.toLowerCase().includes(q) || p.clientName.toLowerCase().includes(q));
  }, [projects, filter, search]);

  const hasFilters = filter !== 'all' || search.trim() !== '';
  const refresh = () => {
    setRefreshing(true);
    void query.refetch().finally(() => setRefreshing(false));
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="projects-screen">
      <FlatList
        data={rows}
        keyExtractor={(p) => p.id}
        refreshing={refreshing}
        onRefresh={refresh}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
        ListHeaderComponent={
          <View style={styles.header}>
            <ScreenHeader
              subtitle={t('projects.activeCount', { count: counts.active })}
              title={t('projects.title')}
              right={
                <IconButton testID="add-project" icon="add" variant="accent" accessibilityLabel={t('projects.add')} onPress={() => router.push('/projects/new')} />
              }
            />
            <OfflineBanner />
            <Input
              placeholder={t('projects.searchPlaceholder')}
              leftIcon="search"
              value={search}
              onChangeText={setSearch}
              returnKeyType="search"
              autoCorrect={false}
              accessibilityLabel={t('projects.searchA11y')}
              right={search ? <IconButton icon="close" variant="plain" size={16} accessibilityLabel={t('common.clearSearch')} onPress={() => setSearch('')} /> : null}
            />
            <SegmentedControl<Filter>
              accessibilityLabel={t('projects.filterA11y')}
              layout="scroll"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'active', label: t('projects.status.active'), count: counts.active },
                { value: 'on_hold', label: t('projects.status.on_hold'), count: counts.on_hold },
                { value: 'completed', label: t('projects.status.completed'), count: counts.completed },
                { value: 'all', label: t('projects.filterAll'), count: counts.all },
              ]}
            />
          </View>
        }
        ListEmptyComponent={
          query.isPending ? (
            <LoadingState rows={3} />
          ) : query.isError ? (
            <ErrorState message={t('errors.NETWORK_ERROR')} onRetry={() => void query.refetch()} retrying={query.isFetching} />
          ) : (
          <EmptyState
            icon="folder-open-outline"
            title={t(hasFilters ? 'projects.emptyFiltered' : 'projects.empty')}
            message={t(hasFilters ? 'projects.emptyFilteredHint' : 'projects.emptyHint')}
            actionLabel={hasFilters ? t('common.clearFilters') : t('projects.add')}
            onAction={
              hasFilters
                ? () => {
                    setFilter('all');
                    setSearch('');
                  }
                : () => router.push('/projects/new')
            }
          />
          )
        }
        renderItem={({ item }) => (
          <ProjectCard
            project={item}
            clientName={item.clientName || t('common.unknownClient')}
            trackedSeconds={item.stats.trackedSeconds}
            unbilled={item.stats.unbilled}
            isTracking={trackingProjectId === item.id}
            onPress={() => router.push({ pathname: '/projects/[id]', params: { id: item.id } })}
          />
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
