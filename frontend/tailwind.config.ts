import type { Config } from "tailwindcss";
import defaultTheme from "tailwindcss/defaultTheme";

const config: Config = {
    darkMode: ["class"],
    content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
  	extend: {
  		colors: {
  			surface: {
  				deep: '#F5F5F7',
  				card: '#FFFFFF',
  				elevated: '#F0F0F2',
  				border: '#E5E7EB'
  			},
  			text: {
  				primary: '#111827',
  				secondary: '#6B7280',
  				muted: '#9CA3AF',
  				inverse: '#F8FAFC'
  			},
  			accent: {
  				live: '#22C55E',
  				brand: '#10B981',
  				futures: '#8B5CF6',
  				warning: '#F59E0B',
  				danger: '#EF4444',
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			snow: '#F5F5F7',
  			graphite: '#111827',
  			slate: '#6B7280',
  			silver: '#9CA3AF',
  			mist: '#E5E7EB',
  			ink: '#111827',
  			charcoal: '#6B7280',
  			fog: '#F0F0F2',
  			forest: '#22C55E',
  			rust: '#EF4444',
  			emerald: '#10B981',
  			amber: '#F59E0B',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		},
  		fontFamily: {
  			sans: [
  				'Inter',
                    ...defaultTheme.fontFamily.sans
                ],
  			mono: [
  				'var(--font-jetbrains-mono)',
  				'SF Mono',
                    ...defaultTheme.fontFamily.mono
                ]
  		},
  		fontSize: {
  			'prob-hero': [
  				'36px',
  				{
  					lineHeight: '1',
  					letterSpacing: '-0.03em',
  					fontWeight: '700'
  				}
  			],
  			'prob-lg': [
  				'28px',
  				{
  					lineHeight: '1',
  					letterSpacing: '-0.02em',
  					fontWeight: '700'
  				}
  			],
  			'prob-md': [
  				'20px',
  				{
  					lineHeight: '1',
  					letterSpacing: '-0.02em',
  					fontWeight: '700'
  				}
  			],
  			'prob-sm': [
  				'16px',
  				{
  					lineHeight: '1',
  					letterSpacing: '-0.01em',
  					fontWeight: '700'
  				}
  			],
  			display: [
  				'48px',
  				{
  					lineHeight: '1.1',
  					letterSpacing: '-0.02em',
  					fontWeight: '700'
  				}
  			],
  			'title-1': [
  				'28px',
  				{
  					lineHeight: '1.2',
  					letterSpacing: '-0.01em',
  					fontWeight: '600'
  				}
  			],
  			'title-2': [
  				'22px',
  				{
  					lineHeight: '1.25',
  					letterSpacing: '-0.01em',
  					fontWeight: '600'
  				}
  			],
  			'title-3': [
  				'18px',
  				{
  					lineHeight: '1.3',
  					letterSpacing: '0',
  					fontWeight: '600'
  				}
  			],
  			body: [
  				'16px',
  				{
  					lineHeight: '1.5',
  					letterSpacing: '0',
  					fontWeight: '400'
  				}
  			],
  			'body-strong': [
  				'16px',
  				{
  					lineHeight: '1.5',
  					letterSpacing: '0',
  					fontWeight: '600'
  				}
  			],
  			caption: [
  				'14px',
  				{
  					lineHeight: '1.4',
  					letterSpacing: '0.01em',
  					fontWeight: '400'
  				}
  			],
  			'caption-strong': [
  				'14px',
  				{
  					lineHeight: '1.4',
  					letterSpacing: '0.01em',
  					fontWeight: '600'
  				}
  			],
  			micro: [
  				'12px',
  				{
  					lineHeight: '1.3',
  					letterSpacing: '0.02em',
  					fontWeight: '500'
  				}
  			],
  			'micro-xs': [
  				'10px',
  				{
  					lineHeight: '1.2',
  					letterSpacing: '0.04em',
  					fontWeight: '600'
  				}
  			]
  		},
  		spacing: {
  			'space-1': '4px',
  			'space-2': '8px',
  			'space-3': '12px',
  			'space-4': '16px',
  			'space-5': '20px',
  			'space-6': '24px',
  			'space-8': '32px',
  			'space-10': '40px',
  			'space-12': '48px',
  			'space-16': '64px'
  		},
  		boxShadow: {
  			card: '0 1px 2px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.03)',
  			'card-hover': '0 4px 16px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.06)',
  			glow: '0 0 20px rgba(16, 185, 129, 0.15)'
  		},
  		borderRadius: {
  			card: '10px',
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		transitionDuration: {
  			fast: '150ms',
  			base: '200ms',
  			slow: '300ms',
  			probability: '400ms'
  		},
  		maxWidth: {
  			content: '1200px'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
