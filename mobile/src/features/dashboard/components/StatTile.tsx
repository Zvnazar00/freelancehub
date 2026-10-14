import { StyleSheet, View } from 'react-native';

import { AppText, Card, Icon, type IconName } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export interface StatTileProps {
  icon: IconName;
  label: string;
  value: string;
  hint?: string;
}

export function StatTile({ icon, label, value, hint }: StatTileProps) {
  return (
    <Card style={styles.tile} padding="md">
      <View style={styles.iconBox}>
        <Icon name={icon} size={16} color="accentText" />
      </View>
      <AppText variant="caption" color="textSecondary">
        {label}
      </AppText>
      <AppText variant="monoLarge" numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7} style={styles.value}>
        {value}
      </AppText>
      {hint ? (
        <AppText variant="caption" color="textMuted" numberOfLines={1}>
          {hint}
        </AppText>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  tile: { flex: 1, gap: spacing.xs },
  value: { fontSize: 22, lineHeight: 28 },
  iconBox: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    backgroundColor: colors.accentSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xs,
  },
});
