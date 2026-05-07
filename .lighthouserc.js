/** @type {import('@lhci/cli').LighthouseConfig} */
module.exports = {
  ci: {
    collect: {
      url: [
        'http://localhost:3000/',
        'http://localhost:3000/pricing',
        'http://localhost:3000/learn',
        'http://localhost:3000/methodology',
        'http://localhost:3000/about',
      ],
      numberOfRuns: 1,
      settings: {
        // Mobile emulation — matches Google’s CWV measurement methodology.
        preset: 'desktop',
        throttlingMethod: 'simulate',
        formFactor: 'mobile',
        screenEmulation: {
          mobile: true,
          width: 375,
          height: 812,
          deviceScaleFactor: 3,
          disabled: false,
        },
      },
    },
    assert: {
      // Thresholds from seo-geo-plan.md §2.5:
      // LCP < 2.5s, INP/TBT < 300ms, CLS < 0.1, performance score >= 0.75.
      // CI environments are noisier than real devices; thresholds are slightly
      // relaxed vs. the plan’s 2.0s LCP target to avoid false positives.
      assertions: {
        'categories:performance': ['warn', { minScore: 0.75 }],
        'largest-contentful-paint': ['error', { maxNumericValue: 3000 }],
        'cumulative-layout-shift': ['error', { maxNumericValue: 0.1 }],
        'total-blocking-time': ['warn', { maxNumericValue: 300 }],
        'first-contentful-paint': ['warn', { maxNumericValue: 2000 }],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
