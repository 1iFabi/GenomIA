/* Adapted from Bklit UI's chart-animation registry component (MIT). */
import { useEffect, useState } from 'react';

export function useEnterComplete(mountProgress) {
  const [complete, setComplete] = useState(() => mountProgress.get() >= 1);

  useEffect(() => {
    if (mountProgress.get() >= 1) {
      setComplete(true);
      return undefined;
    }

    return mountProgress.on('change', (value) => {
      if (value >= 1) setComplete(true);
    });
  }, [mountProgress]);

  return complete;
}
