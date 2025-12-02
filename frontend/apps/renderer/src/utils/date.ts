export function formatKST(datetime: string | Date): string {
  const date = typeof datetime === 'string' ? new Date(datetime) : datetime

  const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000)

  const yyyy = kst.getFullYear()
  const mm = String(kst.getMonth() + 1).padStart(2, '0')
  const dd = String(kst.getDate()).padStart(2, '0')
  const hh = String(kst.getHours()).padStart(2, '0')
  const min = String(kst.getMinutes()).padStart(2, '0')
  const ss = String(kst.getSeconds()).padStart(2, '0')

  return `${yyyy}-${mm}-${dd} ${hh}:${min}:${ss}`
}