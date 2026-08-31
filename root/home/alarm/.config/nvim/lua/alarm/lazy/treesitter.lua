return {
	{
		"nvim-treesitter/nvim-treesitter",
		branch = "main",
		build = ":TSUpdate",
		config = function()
			-- require("nvim-treesitter.configs").setup({
			-- 	ensure_installed = {
			-- 		"bash",
			-- 		"c_sharp",
			-- 		"css",
			-- 		"dockerfile",
			-- 		"editorconfig",
			-- 		"git_rebase",
			-- 		"gitcommit",
			-- 		"gitignore",
			-- 		"html",
			-- 		"java",
			-- 		"javascript",
			-- 		"jinja",
			-- 		"json",
			-- 		"kotlin",
			-- 		"lua",
			-- 		"markdown",
			-- 		"markdown_inline",
			-- 		"nginx",
			-- 		"powershell",
			-- 		"proto",
			-- 		"python",
			-- 		"razor",
			-- 		"regex",
			-- 		"scss",
			-- 		"terraform",
			-- 		"tmux",
			-- 		"tsx",
			-- 		"typescript",
			-- 		"vue",
			-- 		"vim",
			-- 	},
			-- 	auto_install = true,
			-- 	indent = {
			-- 		enable = true,
			-- 	},
			-- 	highlight = {
			-- 		enable = false,
			-- 	},
			-- 	disable = function(_, buf)
			-- 		local max_filesize = 100 * 1024 -- 100 KB
			-- 		local ok, stats = pcall(vim.loop.fs_stat, vim.api.nvim_buf_get_name(buf))
			-- 		if ok and stats and stats.size > max_filesize then
			-- 			return true
			-- 		end
			-- 	end,
			-- })
			require('nvim-treesitter').install {
				"bash",
				"c_sharp",
				"css",
				"dockerfile",
				"editorconfig",
				"git_rebase",
				"gitcommit",
				"gitignore",
				"html",
				"java",
				"javascript",
				"jinja",
				"json",
				"kotlin",
				"lua",
				"markdown",
				"markdown_inline",
				"nginx",
				"powershell",
				"proto",
				"python",
				"razor",
				"regex",
				"scss",
				"terraform",
				"tmux",
				"tsx",
				"typescript",
				"vue",
				"vim",
			}

			vim.api.nvim_create_autocmd('User', {
				pattern = 'TSUpdate',
				callback = function()
					require("nvim-treesitter.parsers").templ = {
						install_info = {
							url = "https://github.com/vrischmann/tree-sitter-templ.git",
							files = { "src/parser.c", "src/scanner.c" },
							branch = "master",
						},
					}
				end
			})

			vim.treesitter.language.register("templ", "templ")
			vim.api.nvim_create_autocmd('FileType', {
				pattern = '*',
				callback = function() pcall(vim.treesitter.start) end,
			})
		end,
	},

	{
		"nvim-treesitter/nvim-treesitter-context",
		after = "nvim-treesitter",
		config = function()
			require("treesitter-context").setup({
				enable = true, -- Enable this plugin (Can be enabled/disabled later via commands)
				multiwindow = false, -- Enable multiwindow support.
				max_lines = 0, -- How many lines the window should span. Values <= 0 mean no limit.
				min_window_height = 0, -- Minimum editor window height to enable context. Values <= 0 mean no limit.
				line_numbers = true,
				multiline_threshold = 20, -- Maximum number of lines to show for a single context
				trim_scope = "outer", -- Which context lines to discard if `max_lines` is exceeded. Choices: 'inner', 'outer'
				mode = "cursor", -- Line used to calculate context. Choices: 'cursor', 'topline'
				-- Separator between context and content. Should be a single character string, like '-'.
				-- When separator is set, the context will only show up when there are at least 2 lines above cursorline.
				separator = nil,
				zindex = 20, -- The Z-index of the context window
				on_attach = nil, -- (fun(buf: integer): boolean) return false to disable attaching
			})
		end,
	},
}

