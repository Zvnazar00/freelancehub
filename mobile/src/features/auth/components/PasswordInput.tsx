import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { IconButton, Input, type InputProps } from '@/shared/ui';

export function PasswordInput(props: InputProps) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  return (
    <Input
      {...props}
      secureTextEntry={!visible}
      autoCapitalize="none"
      autoCorrect={false}
      leftIcon="lock-closed-outline"
      right={
        <IconButton
          icon={visible ? 'eye-off-outline' : 'eye-outline'}
          variant="plain"
          size={18}
          accessibilityLabel={t(visible ? 'auth.hidePassword' : 'auth.showPassword')}
          onPress={() => setVisible((v) => !v)}
        />
      }
    />
  );
}
