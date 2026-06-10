"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

export default function PrivacyPage() {
  usePageTracking({ pageType: "privacy", pageTitle: "Privacy Policy" });
  useScrollDepth({ pageType: "privacy" });
  useEngagementTime({ pageType: "privacy" });

  return (
    <div className="max-w-3xl mx-auto space-y-8 px-4 py-6">
      {/* Header */}
      <div className="space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">Privacy Policy</h1>
        <p className="text-text-secondary">
          Last updated: May 17, 2026
        </p>
      </div>

      {/* What Bain Luck Does */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          What Bain Luck Does
        </h2>
        <p className="text-text-secondary leading-relaxed">
          Bain Luck is a prediction market discovery platform that translates
          betting odds and prediction markets into simple probabilities. We
          aggregate publicly available data from multiple sources so you can see
          what the world thinks will happen — across sports, politics, economics,
          entertainment, weather, and more.
        </p>
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <p className="text-sm text-text-primary leading-relaxed font-medium">
            Bain Luck displays prediction market probabilities for informational
            purposes only. It does not facilitate, encourage, or enable betting,
            wagering, or gambling of any kind. No real money is exchanged through
            the app. Users do not place bets, purchase contracts, or risk funds
            in any way.
          </p>
        </div>
      </section>

      {/* Information We Collect */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Information We Collect
        </h2>
        <p className="text-text-secondary leading-relaxed">
          We collect only the information necessary to provide and improve the
          Bain Luck experience. Here is exactly what we collect and why.
        </p>
        <div className="space-y-4">
          {/* Account Data */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">
              Account Information
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              If you sign in with Google or Apple, we receive your email address,
              display name, and profile photo URL from your identity provider. We
              store this information in our database to create and identify your
              account, sync your predictions across devices, and optionally
              notify you about bug reports you submit. We do not access your
              contacts, calendar, files, or any other data from your Google or
              Apple account.
            </p>
          </div>

          {/* Prediction Activity */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">
              Prediction Activity
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              When you play the Higher/Lower prediction game, we save your
              guesses, prediction accuracy, and streaks. This data is linked to
              your account if you are signed in, or to an anonymous session
              identifier if you are not. We use this data to display your
              personal stats, leaderboard position, and prediction history.
            </p>
          </div>

          {/* Analytics */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">
              Analytics
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              We use Google Analytics 4 (via Firebase) to understand how people
              use Bain Luck and to improve the product. This includes page views,
              scroll depth, engagement time, screen tracking, and prediction
              submission events. All analytics data is anonymous by default. We
              do not send any personally identifiable information (PII) to
              Google. Analytics data is used in aggregate to guide product
              decisions, not to build individual user profiles.
            </p>
          </div>

          {/* Device Info */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">
              Device Information (Bug Reports Only)
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              When you initiate a bug report by shaking your device or using the
              keyboard shortcut, we collect your device model, operating system
              version, app version, network connection type, and the page you
              were viewing. A screenshot is also captured. This information is
              sent only when you explicitly trigger a bug report and is used
              solely to diagnose and fix issues. It is never collected in the
              background.
            </p>
          </div>

          {/* Push Notifications */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">
              Push Notification Tokens
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              If you enable push notifications on iOS or macOS, we store your
              Apple Push Notification service (APNS) device token to send you
              notifications. You can disable push notifications at any time in
              your device Settings, which will stop all notifications from Bain
              Luck.
            </p>
          </div>

          {/* Category Preferences */}
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">
              Category Preferences
            </h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              You can select sport and topic interests to personalize your
              Discover feed. For signed-in users, these preferences are stored on
              our servers so they sync across devices. For anonymous users,
              preferences are stored locally in your browser (localStorage) and
              are not transmitted to our servers.
            </p>
          </div>
        </div>
      </section>

      {/* What We Do NOT Collect */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Information We Do Not Collect
        </h2>
        <ul className="space-y-2 text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="text-accent-live mt-0.5 flex-shrink-0">
              &#10003;
            </span>
            <span>
              <strong>No location data</strong> — we do not request or access
              your GPS, Wi-Fi, or IP-based location
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-live mt-0.5 flex-shrink-0">
              &#10003;
            </span>
            <span>
              <strong>No contacts</strong> — we never access your address book
              or contact list
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-live mt-0.5 flex-shrink-0">
              &#10003;
            </span>
            <span>
              <strong>No health or fitness data</strong> — we do not access
              HealthKit or any health-related information
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-live mt-0.5 flex-shrink-0">
              &#10003;
            </span>
            <span>
              <strong>No financial data</strong> — we do not collect payment
              information, bank accounts, or financial records
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-live mt-0.5 flex-shrink-0">
              &#10003;
            </span>
            <span>
              <strong>No cross-app tracking</strong> — we do not use the App
              Tracking Transparency (ATT) framework or advertising identifiers
              (IDFA)
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-live mt-0.5 flex-shrink-0">
              &#10003;
            </span>
            <span>
              <strong>No data sold to third parties</strong> — we will never sell,
              rent, or trade your personal information to any third party
            </span>
          </li>
        </ul>
      </section>

      {/* How We Use Your Information */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          How We Use Your Information
        </h2>
        <ul className="space-y-2 text-sm text-text-secondary list-disc pl-5">
          <li>
            <strong>Provide the service:</strong> display probabilities, track
            your predictions, sync data across your devices, and personalize your
            feed
          </li>
          <li>
            <strong>Improve the product:</strong> understand which features are
            used, identify performance issues, and prioritize development
          </li>
          <li>
            <strong>Fix bugs:</strong> diagnose issues reported through the
            in-app bug reporting feature
          </li>
          <li>
            <strong>Communicate:</strong> send push notifications (if enabled)
            and respond to bug reports or support requests
          </li>
        </ul>
      </section>

      {/* Third-Party Services */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Third-Party Services
        </h2>
        <p className="text-text-secondary leading-relaxed">
          We use the following third-party services. Each operates under its own
          privacy policy. We only share the minimum data necessary for each
          service to function.
        </p>
        <div className="space-y-4">
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2 text-sm">
              Services That Receive User Data
            </h3>
            <ul className="space-y-2 text-sm text-text-secondary">
              <li>
                <strong>Firebase Authentication</strong> (Google) — handles
                Google and Apple Sign-In. Receives authentication credentials
                during sign-in only.
              </li>
              <li>
                <strong>Google Analytics 4 / Firebase Analytics</strong>{" "}
                (Google) — receives anonymous usage events (page views,
                engagement time, interaction events). No PII is transmitted.
              </li>
              <li>
                <strong>Firebase Crashlytics</strong> (Google) — collects
                crash reports and diagnostics data from the iOS app to help
                us identify and fix stability issues. May include device
                model, OS version, and crash stack traces. User ID is
                attached only when signed in, to help diagnose
                account-specific issues.
              </li>
              <li>
                <strong>Sentry</strong> — collects error reports and
                performance data from the web application and API. Includes
                request metadata (URL, status code, timing) but no PII.
              </li>
              <li>
                <strong>Vercel</strong> — hosts the web application. Processes
                standard HTTP requests.
              </li>
              <li>
                <strong>Heroku</strong> (Salesforce) — hosts the API server and
                database.
              </li>
            </ul>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2 text-sm">
              Services We Read From (No User Data Sent)
            </h3>
            <ul className="space-y-2 text-sm text-text-secondary">
              <li>
                <strong>Kalshi</strong> — prediction market data. We read
                publicly available market prices. No user data is sent to Kalshi.
              </li>
              <li>
                <strong>Polymarket</strong> — prediction market data. We read
                publicly available market prices. No user data is sent to
                Polymarket.
              </li>
              <li>
                <strong>Pexels</strong> — stock photography for feed cards. No
                user data is sent to Pexels.
              </li>
              <li>
                <strong>OpenAI</strong> — generates market description text. No
                user data, personal information, or prediction activity is sent
                to OpenAI. Only market metadata (event names, odds) is processed.
              </li>
              <li>
                <strong>TMDB</strong> — movie and TV metadata. No user data is
                sent to TMDB.
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Data Storage & Security */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Data Storage and Security
        </h2>
        <p className="text-text-secondary leading-relaxed">
          Your data is stored on secure servers hosted by Heroku (Salesforce).
          All data is transmitted over HTTPS/TLS encryption. Authentication
          tokens are stored securely in the iOS Keychain on Apple devices and in
          browser session storage on the web. We follow industry-standard
          practices to protect your information, but no method of electronic
          storage is 100% secure.
        </p>
      </section>

      {/* Data Retention & Deletion */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Data Retention and Deletion
        </h2>
        <p className="text-text-secondary leading-relaxed">
          Your prediction history, account information, and preferences are
          retained for as long as your account is active. Anonymized analytics
          data is retained in aggregate by Google Analytics per their standard
          retention policies.
        </p>
        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <h3 className="font-semibold text-text-primary mb-2 text-sm">
            Deleting Your Data
          </h3>
          <p className="text-sm text-text-secondary leading-relaxed">
            You can delete your account and all associated data at any time from
            the My Stuff tab in the app. You may also request deletion by
            emailing{" "}
            <a
              href="mailto:privacy@bainluck.com"
              className="text-accent-brand underline hover:no-underline"
            >
              privacy@bainluck.com
            </a>
            . Upon deletion, we remove your account information, prediction
            history, preferences, and any stored push notification tokens. This
            action is permanent and cannot be undone.
          </p>
        </div>
      </section>

      {/* Children */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Children&apos;s Privacy
        </h2>
        <p className="text-text-secondary leading-relaxed">
          Bain Luck is not directed at children under 13 (or under 16 in the
          European Economic Area). We do not knowingly collect personal
          information from children. If you believe a child has provided us with
          personal information, please contact us at{" "}
          <a
            href="mailto:privacy@bainluck.com"
            className="text-accent-brand underline hover:no-underline"
          >
            privacy@bainluck.com
          </a>{" "}
          and we will promptly delete that information.
        </p>
      </section>

      {/* Your Rights */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">Your Rights</h2>
        <p className="text-text-secondary leading-relaxed">
          Depending on your jurisdiction, you may have the right to:
        </p>
        <ul className="space-y-2 text-sm text-text-secondary list-disc pl-5">
          <li>Access the personal data we hold about you</li>
          <li>Request correction of inaccurate data</li>
          <li>Request deletion of your data</li>
          <li>Object to or restrict processing of your data</li>
          <li>Request a portable copy of your data</li>
        </ul>
        <p className="text-text-secondary leading-relaxed">
          To exercise any of these rights, contact us at{" "}
          <a
            href="mailto:privacy@bainluck.com"
            className="text-accent-brand underline hover:no-underline"
          >
            privacy@bainluck.com
          </a>
          . We will respond within 30 days.
        </p>
      </section>

      {/* Changes to This Policy */}
      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">
          Changes to This Policy
        </h2>
        <p className="text-text-secondary leading-relaxed">
          We may update this privacy policy from time to time. When we do, we
          will revise the &quot;Last updated&quot; date at the top of this page.
          We encourage you to review this page periodically for any changes.
          Continued use of Bain Luck after changes are posted constitutes
          acceptance of the updated policy.
        </p>
      </section>

      {/* Contact */}
      <section className="space-y-3 pb-8">
        <h2 className="text-xl font-bold text-text-primary">Contact Us</h2>
        <p className="text-text-secondary leading-relaxed">
          If you have questions, concerns, or requests regarding this privacy
          policy or our data practices, please contact us at{" "}
          <a
            href="mailto:privacy@bainluck.com"
            className="text-accent-brand underline hover:no-underline"
          >
            privacy@bainluck.com
          </a>
          .
        </p>
      </section>
    </div>
  );
}
