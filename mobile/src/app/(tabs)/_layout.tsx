import { router } from 'expo-router';
import { BottomTabBar, Tabs, type BottomTabBarProps } from 'expo-router/js-tabs';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View, type ColorValue } from 'react-native';

import { useTimerCommands } from '@/features/timer/api';
import { useActiveTimer } from '@/features/timer/hooks';
import { MiniTimerBar } from '@/features/timer/components/MiniTimerBar';
import { Icon, type IconName } from '@/shared/ui';
import { colors, fontFamilies } from '@/shared/theme';

function TabIcon({ name, color, dot = false }: { name: IconName; color: ColorValue; dot?: boolean }) {
  return (
    <View style={styles.iconBox}>
      <Icon name={name} size={22} rawColor={color} />
      {dot ? <View style={styles.dot} /> : null}
    </View>
  );
}

function TabBarWithTimer(props: BottomTabBarProps) {
  const { t } = useTranslation();
  const active = useActiveTimer();
  const commands = useTimerCommands();
  const currentRoute = props.state.routes[props.state.index]?.name;
  const showMini = active !== null && currentRoute !== 'time';

  return (
    <View>
      {showMini && active ? (
        <MiniTimerBar
          projectName={active.entry.project.name || t('common.unknownProject')}
          projectColor={active.entry.project.color || colors.accent}
          description={active.entry.description}
          seconds={active.seconds}
          status={active.entry.status}
          onOpen={() => router.navigate('/time')}
          onToggle={() =>
            void commands.run({ kind: active.entry.status === 'running' ? 'pause' : 'resume', entryId: active.entry.id })
          }
        />
      ) : null}
      <BottomTabBar {...props} />
    </View>
  );
}

function TimeTabIcon({ color }: { color: ColorValue }) {
  const active = useActiveTimer();
  return <TabIcon name={active ? 'timer' : 'timer-outline'} color={color} dot={active?.entry.status === 'running'} />;
}

export default function TabsLayout() {
  const { t } = useTranslation();
  return (
    <Tabs
      tabBar={(props) => <TabBarWithTimer {...props} />}
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.bg },
        tabBarActiveTintColor: colors.accentText,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: {
          backgroundColor: colors.surface1,
          borderTopColor: colors.border,
          borderTopWidth: StyleSheet.hairlineWidth,
        },
        tabBarIconStyle: { height: 24 },
        tabBarLabelStyle: { fontFamily: fontFamilies.medium, fontSize: 11, lineHeight: 13 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: t('tabs.dashboard'), tabBarIcon: ({ color, focused }) => <TabIcon name={focused ? 'grid' : 'grid-outline'} color={color} /> }}
      />
      <Tabs.Screen
        name="projects"
        options={{ title: t('tabs.projects'), tabBarIcon: ({ color, focused }) => <TabIcon name={focused ? 'folder' : 'folder-outline'} color={color} /> }}
      />
      <Tabs.Screen name="time" options={{ title: t('tabs.time'), tabBarIcon: ({ color }) => <TimeTabIcon color={color} /> }} />
      <Tabs.Screen
        name="clients"
        options={{ title: t('tabs.clients'), tabBarIcon: ({ color, focused }) => <TabIcon name={focused ? 'people' : 'people-outline'} color={color} /> }}
      />
      <Tabs.Screen
        name="settings"
        options={{ title: t('tabs.settings'), tabBarIcon: ({ color, focused }) => <TabIcon name={focused ? 'settings' : 'settings-outline'} color={color} /> }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  iconBox: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  dot: {
    position: 'absolute',
    top: -1,
    right: -3,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.success,
    borderWidth: 1.5,
    borderColor: colors.surface1,
  },
});
