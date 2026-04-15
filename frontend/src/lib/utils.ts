import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function generateId(): string {
  return crypto.randomUUID()
}

export function truncate(str: string, n: number): string {
  return str.length > n ? str.slice(0, n) + '…' : str
}

export function formatDate(d: Date): string {
  return new Intl.DateTimeFormat('es-CO', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(d)
}
