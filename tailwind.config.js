/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './dashboard/templates/**/*.html',
    './dashboard/static/**/*.js'
  ],
  theme: {
    extend: {
      "colors": {
          "secondary-fixed": "var(--color-secondary-fixed)",
          "surface-container-low": "var(--color-surface-container-low)",
          "surface-tint": "var(--color-surface-tint)",
          "background": "var(--color-background)",
          "surface-dim": "var(--color-surface-dim)",
          "on-tertiary-container": "var(--color-on-tertiary-container)",
          "tertiary-fixed": "var(--color-tertiary-fixed)",
          "on-primary-container": "var(--color-on-primary-container)",
          "primary-container": "var(--color-primary-container)",
          "on-tertiary-fixed-variant": "var(--color-on-tertiary-fixed-variant)",
          "tertiary": "var(--color-tertiary)",
          "tertiary-fixed-dim": "var(--color-tertiary-fixed-dim)",
          "surface": "var(--color-surface)",
          "surface-variant": "var(--color-surface-variant)",
          "on-secondary-fixed": "var(--color-on-secondary-fixed)",
          "surface-container-high": "var(--color-surface-container-high)",
          "on-secondary-container": "var(--color-on-secondary-container)",
          "on-primary-fixed-variant": "var(--color-on-primary-fixed-variant)",
          "tertiary-container": "var(--color-tertiary-container)",
          "outline": "var(--color-outline)",
          "on-error-container": "var(--color-on-error-container)",
          "surface-container-highest": "var(--color-surface-container-highest)",
          "inverse-primary": "var(--color-inverse-primary)",
          "surface-container": "var(--color-surface-container)",
          "primary-fixed-dim": "var(--color-primary-fixed-dim)",
          "outline-variant": "var(--color-outline-variant)",
          "on-secondary-fixed-variant": "var(--color-on-secondary-fixed-variant)",
          "secondary-container": "var(--color-secondary-container)",
          "secondary": "var(--color-secondary)",
          "on-primary-fixed": "var(--color-on-primary-fixed)",
          "error-container": "var(--color-error-container)",
          "secondary-fixed-dim": "var(--color-secondary-fixed-dim)",
          "inverse-on-surface": "var(--color-inverse-on-surface)",
          "surface-bright": "var(--color-surface-bright)",
          "inverse-surface": "var(--color-inverse-surface)",
          "primary-fixed": "var(--color-primary-fixed)",
          "primary": "var(--color-primary)",
          "on-secondary": "var(--color-on-secondary)",
          "on-surface-variant": "var(--color-on-surface-variant)",
          "on-tertiary-fixed": "var(--color-on-tertiary-fixed)",
          "surface-container-lowest": "var(--color-surface-container-lowest)",
          "on-surface": "var(--color-on-surface)",
          "on-background": "var(--color-on-background)",
          "on-error": "var(--color-on-error)",
          "on-tertiary": "var(--color-on-tertiary)",
          "on-primary": "var(--color-on-primary)",
          "error": "var(--color-error)"
      },
      "borderRadius": {
          "DEFAULT": "0.125rem",
          "lg": "0.25rem",
          "xl": "0.5rem",
          "full": "0.75rem"
      },
      "spacing": {
          "gutter": "24px",
          "stack-sm": "8px",
          "base": "4px",
          "stack-md": "16px",
          "stack-lg": "32px",
          "container-max": "1440px",
          "margin": "32px"
      },
      "fontFamily": {
          "headline-lg": ["Geist"],
          "label-mono": ["JetBrains Mono"],
          "body-lg": ["Geist"],
          "headline-lg-mobile": ["Geist"],
          "body-md": ["Geist"],
          "headline-md": ["Geist"],
          "display-lg": ["Geist"]
      },
      "fontSize": {
          "headline-lg": ["30px", { "lineHeight": "36px", "letterSpacing": "-0.01em", "fontWeight": "600" }],
          "label-mono": ["12px", { "lineHeight": "16px", "letterSpacing": "0.05em", "fontWeight": "500" }],
          "body-lg": ["16px", { "lineHeight": "24px", "fontWeight": "400" }],
          "headline-lg-mobile": ["24px", { "lineHeight": "30px", "fontWeight": "600" }],
          "body-md": ["14px", { "lineHeight": "20px", "fontWeight": "400" }],
          "headline-md": ["24px", { "lineHeight": "32px", "fontWeight": "600" }],
          "display-lg": ["48px", { "lineHeight": "1.1", "letterSpacing": "-0.02em", "fontWeight": "700" }]
      }
    }
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries')
  ],
}
