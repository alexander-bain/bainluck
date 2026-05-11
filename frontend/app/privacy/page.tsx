"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

export default function PrivacyPage() {
  usePageTracking({ pageType: "privacy", pageTitle: "Privacy Policy" });
  useScrollDepth({ pageType: "privacy" });
  useEngagementTime({ pageType: "privacy" });

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">Privacy Policy</h1>
        <p className="text-text-secondary">Last updated: May 11, 2026</p>
      </div>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">What Bain Luck Does</h2>
        <p className="text-text-secondary leading-relaxed">
          Bain Luck is a prediction market discovery platform that translates betting odds and prediction markets into simple probabilities. We aggregate publicly available data from multiple sources so you can see what the world thinks will happen — across sports, politics, economics, weather, and more.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">What We Collect</h2>
        <div className="space-y-4">
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">Account Information</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              If you sign in with Google or Apple, we receive your name, email, and profile photo from your identity provider. We use this to create your account and sync your predictions across devices. We do not access your contacts, calendar, or any other data from your Google or Apple account.
            </p>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">Predictions & Activity</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              When you play the Higher/Lower prediction game, we save your guesses, streaks, and prediction accuracy. This data is tied to your account (if signed in) or an anonymous session identifier (if not). We use it to show your stats and streaks.
            </p>
          </div>
          <div className="bg-surface-card border border-surface-border rounded-xl p-4">
            <h3 className="font-semibold text-text-primary mb-2">Analytics</h3>
            <p className="text-sm text-text-secondary leading-relaxed">
              We use Firebase Analytics (Google) to understand which features people use and how the app performs. This includes page views, screen time, and interaction events. Analytics data is aggregated and not used to build individual user profiles.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">What We Do Not Collect</h2>
        <ul className="space-y-2 text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="text-green-600 mt-0.5">&#10003;</span>
            <span>No location data</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-green-600 mt-0.5">&#10003;</span>
            <span>No contacts or address book access</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-green-600 mt-0.5">&#10003;</span>
            <span>No advertising identifiers (IDFA)</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-green-600 mt-0.5">&#10003;</span>
            <span>No cross-app tracking</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-green-600 mt-0.5">&#10003;</span>
            <span>No data sold to third parties</span>
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">Third-Party Services</h2>
        <p className="text-text-secondary leading-relaxed">
          We use the following third-party services, each with their own privacy policies:
        </p>
        <ul className="space-y-1 text-text-secondary text-sm">
          <li><strong>Firebase Authentication</strong> (Google) — account sign-in</li>
          <li><strong>Firebase Analytics</strong> (Google) — usage analytics</li>
          <li><strong>Vercel</strong> — web hosting</li>
          <li><strong>Heroku</strong> (Salesforce) — API hosting</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">Data Retention & Deletion</h2>
        <p className="text-text-secondary leading-relaxed">
          Your prediction history and account data are retained as long as your account is active. You can delete your account and all associated data at any time from the My Stuff tab in the app, or by contacting us at the email below.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-text-primary">Children</h2>
        <p className="text-text-secondary leading-relaxed">
          Bain Luck is not directed at children under 13. We do not knowingly collect personal information from children under 13.
        </p>
      </section>

      <section className="space-y-3 pb-8">
        <h2 className="text-xl font-bold text-text-primary">Contact</h2>
        <p className="text-text-secondary leading-relaxed">
          Questions about this policy? Email{" "}
          <a href="mailto:privacy@bainluck.com" className="text-accent-brand underline hover:no-underline">
            privacy@bainluck.com
          </a>
        </p>
      </section>
    </div>
  );
}
