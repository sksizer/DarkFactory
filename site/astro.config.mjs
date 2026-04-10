// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightClientMermaid from '@pasqal-io/starlight-client-mermaid';

// https://astro.build/config
export default defineConfig({
	integrations: [
		starlight({
			title: 'DarkFactory',
			plugins: [starlightClientMermaid()],
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/sksizer/DarkFactory',
				},
			],
			customCss: ['./src/styles/custom.css'],
			expressiveCode: {
				themes: ['dracula', 'github-light'],
				useStarlightDarkModeSwitch: true,
				useStarlightUiThemeColors: true,
				styleOverrides: {
					borderRadius: '0.5rem',
					codeFontFamily: "'JetBrains Mono', 'Fira Code', monospace",
				},
			},
			sidebar: [
				{
					label: 'Getting Started',
					items: [
						{ slug: 'getting-started' },
						{ slug: 'getting-started/installation' },
						{ slug: 'getting-started/first-prd' },
						{ slug: 'getting-started/first-workflow' },
					],
				},
				{
					label: 'Concepts',
					items: [
						{ slug: 'concepts/prds' },
						{ slug: 'concepts/dag' },
						{ slug: 'concepts/workflows' },
						{ slug: 'concepts/status-lifecycle' },
						{ slug: 'concepts/agent-model' },
						{ slug: 'concepts/worktrees' },
						{ slug: 'concepts/containment' },
						{ slug: 'concepts/config-cascade' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ slug: 'guides/writing-prds' },
						{ slug: 'guides/custom-workflows' },
						{ slug: 'guides/system-operations' },
						{ slug: 'guides/dag-execution' },
						{ slug: 'guides/agent-prompts' },
						{ slug: 'guides/verification' },
						{ slug: 'guides/rework' },
						{ slug: 'guides/reconcile' },
						{ slug: 'guides/event-logging' },
						{ slug: 'guides/troubleshooting' },
					],
				},
				{
					label: 'CLI Reference',
					items: [
						{ slug: 'reference/cli' },
						{
							label: 'Commands',
							autogenerate: { directory: 'reference/cli' },
						},
					],
				},
				{
					label: 'API Reference',
					items: [
						{ slug: 'reference/frontmatter' },
						{ slug: 'reference/config' },
						{ slug: 'reference/builtins' },
						{ slug: 'reference/workflow-api' },
						{ slug: 'reference/project-layout' },
					],
				},
				{
					label: 'Architecture',
					items: [
						{ slug: 'architecture/three-layers' },
						{ slug: 'architecture/runner' },
						{ slug: 'architecture/graph-execution' },
						{ slug: 'architecture/extension-points' },
					],
				},
				{
					label: 'Philosophy',
					items: [
						{ slug: 'philosophy/agent-verification' },
						{ slug: 'philosophy/declarative-first' },
						{ slug: 'philosophy/harness-as-safety' },
					],
				},
			],
		}),
	],
});
