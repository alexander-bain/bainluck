/**
 * Type declarations for Apple Sign-In JS SDK.
 * https://developer.apple.com/documentation/sign_in_with_apple/sign_in_with_apple_js
 */

declare namespace AppleID {
  interface AuthI {
    init(config: {
      clientId: string;
      scope?: string;
      redirectURI: string;
      state?: string;
      nonce?: string;
      usePopup?: boolean;
    }): void;

    signIn(): Promise<SignInResponse>;
  }

  interface SignInResponse {
    authorization: {
      code: string;
      id_token: string;
      state?: string;
    };
    /** Only present on first authorization. */
    user?: {
      email?: string;
      name?: {
        firstName?: string;
        lastName?: string;
      };
    };
  }

  const auth: AuthI;
}

interface Window {
  AppleID?: typeof AppleID;
}
