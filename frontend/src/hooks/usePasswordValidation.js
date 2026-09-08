import { useMemo } from 'react';

/**
 * Real-time password strength validation, shared by the Reset and Change
 * password modals.
 */
export function usePasswordValidation(password) {
  return useMemo(
    () => ({
      minLength: password.length >= 10,
      hasUppercase: /[A-Z]/.test(password),
      hasNumber: /[0-9]/.test(password),
      hasSymbol: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    }),
    [password]
  );
}
