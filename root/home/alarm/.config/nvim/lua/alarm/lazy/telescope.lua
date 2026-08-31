return {
    {
        "nvim-telescope/telescope.nvim",
        tag = "v0.2.2",
        dependencies = {
            "nvim-lua/plenary.nvim",
            "BurntSushi/ripgrep",
            "nvim-telescope/telescope-fzf-native.nvim",
        },
        config = function()
            local builtin = require("telescope.builtin")
            local actions = require("telescope.actions")

            local open_after_tree = function(prompt_bufnr)
                vim.defer_fn(function()
                    actions.select_default(prompt_bufnr)
                end, 100) -- Delay allows filetype and plugins to settle before opening
            end

            require("telescope").setup({
                defaults = {
                    mappings = {
                        i = { ["<CR>"] = open_after_tree },
                        n = { ["<CR>"] = open_after_tree },
                    },
                    file_ignore_patterns = { "%__virtual.cs$" },
                },
                pickers = {
                    buffers = {
                        -- initial_mode = "normal",
                        sort_lastused = true,
                        mappings = {
                            n = {
                                ["x"] = "delete_buffer"
                            }
                        }
                    }
                },
            })

            vim.keymap.set("n", "<leader>ff", builtin.find_files, {
                desc = "Telescope find files",
            })
            vim.keymap.set("n", "<leader>fh", function()
                return builtin.find_files({
                    hidden = true,
                    no_ignore = true,
                })
            end, { desc = "Telescope find hidden files" })
            vim.keymap.set("n", "<leader>fg", builtin.live_grep, {
                desc = "Telescope live grep",
            })
            vim.keymap.set("n", "<leader>fb", builtin.buffers, {
                desc = "Telescope buffers",
            })
            vim.keymap.set("n", "<leader>fn", builtin.help_tags, {
                desc = "Telescope help tags",
            })
        end,
    },
    {
        { "nvim-telescope/telescope-fzf-native.nvim", build = "make" },
    },
}

