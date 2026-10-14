import { useTranslation } from 'react-i18next';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Project, Task } from '@/shared/types/domain';
import { AppText, Button, Icon } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export interface PickerProject {
  project: Project;
  clientName: string;
  tasks: Task[];
}

export interface ProjectPickerSheetProps {
  visible: boolean;
  items: PickerProject[];
  selectedProjectId: string | null;
  selectedTaskId: string | null;
  onSelectProject: (projectId: string) => void;
  onSelectTask: (taskId: string | null) => void;
  onClose: () => void;
}

export function ProjectPickerSheet({
  visible,
  items,
  selectedProjectId,
  selectedTaskId,
  onSelectProject,
  onSelectTask,
  onClose,
}: ProjectPickerSheetProps) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const selected = items.find((i) => i.project.id === selectedProjectId);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <Pressable style={styles.overlay} onPress={onClose} accessibilityLabel={t('timer.pickerClose')} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]} accessibilityViewIsModal>
        <View style={styles.handle} />
        <AppText variant="heading" accessibilityRole="header">
          {t('timer.pickerTitle')}
        </AppText>
        <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
          {items.map(({ project, clientName }) => {
            const isSelected = project.id === selectedProjectId;
            return (
              <Pressable
                key={project.id}
                accessibilityRole="radio"
                accessibilityState={{ checked: isSelected }}
                accessibilityLabel={`${project.name}, ${clientName}`}
                onPress={() => onSelectProject(project.id)}
                style={({ pressed }) => [styles.option, isSelected && styles.optionSelected, pressed && styles.optionPressed]}
              >
                <View style={[styles.dot, { backgroundColor: project.color }]} />
                <View style={styles.optionText}>
                  <AppText variant="bodyMedium" numberOfLines={1}>
                    {project.name}
                  </AppText>
                  <AppText variant="caption" color="textMuted" numberOfLines={1}>
                    {clientName}
                  </AppText>
                </View>
                {isSelected ? <Icon name="checkmark-circle" size={20} color="accent" /> : null}
              </Pressable>
            );
          })}

          {selected ? (
            <View style={styles.tasks}>
              <AppText variant="overline" color="textSecondary">
                {t('timer.pickerTask')}
              </AppText>
              <View style={styles.chips}>
                {[{ id: null, title: t('common.noTask') }, ...selected.tasks.filter((t) => t.status !== 'done')].map((t) => {
                  const active = t.id === selectedTaskId;
                  return (
                    <Pressable
                      key={t.id ?? 'none'}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: active }}
                      onPress={() => onSelectTask(t.id)}
                      style={[styles.chip, active && styles.chipActive]}
                    >
                      <AppText variant="captionMedium" color={active ? 'accentText' : 'textSecondary'}>
                        {t.title}
                      </AppText>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ) : null}
        </ScrollView>
        <Button label={t('common.done')} onPress={onClose} fullWidth disabled={!selected} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: colors.overlay },
  sheet: {
    maxHeight: '80%',
    backgroundColor: colors.surface1,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: spacing.md,
  },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong, marginBottom: spacing.sm },
  list: { flexGrow: 0 },
  listContent: { gap: spacing.xs + 2, paddingBottom: spacing.sm },
  option: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.transparent,
  },
  optionSelected: { backgroundColor: colors.accentSoft, borderColor: colors.accentBorder },
  optionPressed: { backgroundColor: colors.surface2 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  optionText: { flex: 1 },
  tasks: { gap: spacing.sm, marginTop: spacing.md },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface2,
  },
  chipActive: { borderColor: colors.accentBorder, backgroundColor: colors.accentSoft },
});
