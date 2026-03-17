import React from 'react'
import type { Severity } from '../types'

interface Props {
  severity: Severity
  size?: 'sm' | 'md'
}

const CONFIG: Record<Severity, { label: string; classes: string }> = {
  error: {
    label: 'Error',
    classes: 'bg-rose-100 text-rose-700 ring-1 ring-rose-200',
  },
  warn: {
    label: 'Warning',
    classes: 'bg-amber-100 text-amber-700 ring-1 ring-amber-200',
  },
  info: {
    label: 'Info',
    classes: 'bg-violet-100 text-violet-700 ring-1 ring-violet-200',
  },
}

export const SeverityBadge: React.FC<Props> = ({ severity, size = 'sm' }) => {
  const { label, classes } = CONFIG[severity] ?? CONFIG.info
  const sizeClasses = size === 'sm'
    ? 'px-2 py-0.5 text-[10px] font-semibold'
    : 'px-2.5 py-1 text-xs font-semibold'

  return (
    <span className={`inline-flex items-center rounded-full uppercase tracking-wide ${sizeClasses} ${classes}`}>
      {label}
    </span>
  )
}
