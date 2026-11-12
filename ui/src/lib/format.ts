/** settings_dialog.human_size 와 같다. */
export function humanSize(num: number): string {
  let step = num
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (step < 1024 || unit === 'GB') {
      return unit === 'B'
        ? `${Math.round(step).toLocaleString('en-US')} ${unit}`
        : `${step.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${unit}`
    }
    step /= 1024
  }
  return `${step} GB`
}
