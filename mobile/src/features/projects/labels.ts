import type { TFunction } from 'i18next';

import { formatMoney } from '@/shared/lib/money';
import type { Project, ProjectStatus, TaskPriority } from '@/shared/types/domain';
import type { BadgeTone } from '@/shared/ui';

export const projectStatusTone: Record<ProjectStatus, BadgeTone> = {
  active: 'success',
  on_hold: 'warning',
  completed: 'neutral',
};

export const priorityTone: Record<TaskPriority, BadgeTone> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
};

export function billingLabel(project: Project, t: TFunction): string {
  switch (project.billingType) {
    case 'hourly':
      return project.hourlyRate ? t('projects.perHour', { rate: formatMoney(project.hourlyRate, project.currency) }) : t('projects.hourly');
    case 'fixed':
      return project.fixedFee
        ? t('projects.fixed', { amount: formatMoney(project.fixedFee, project.currency, { compact: true }) })
        : t('projects.fixedFee');
    case 'non_billable':
      return t('projects.nonBillable');
  }
}
