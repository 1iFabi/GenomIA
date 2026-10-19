export function pickMascotState({ entering, open, hover, sleeping, typing, notFound, found }) {
  if (open) {
    if (typing) return "typing";
    if (notFound) return "notFound";
    if (found) return "found";
    return "open";
  }
  if (hover) return "hover";
  if (sleeping) return "sleep";
  if (entering) return "entrance";
  return "idle";
}
