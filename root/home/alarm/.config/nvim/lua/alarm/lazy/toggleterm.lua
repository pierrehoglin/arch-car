return {
    "akinsho/toggleterm.nvim",
    config = function()
        local term = require("toggleterm")

        term.setup({
            size = 45,
            open_mapping = "<leader>tt",
            insert_mappings = false,
            terminal_mappings = false,
            shade_filetypes = {},
            direction = "horizontal",
            autochdir = true,
            on_open = function(t)
                vim.api.nvim_buf_set_keymap(t.bufnr, "t", "<Esc>", "<c-\\><c-n>", { noremap = true, silent = true })
                --vim.keymap.set("t", "<Esc>", "<c-\\><c-n>", { noremap = true, desc = "Stop terminal input" })
            end,
        })

        local terminal = require("toggleterm.terminal").Terminal
        local dash = terminal:new({
            display_name = "DASH",
            cmd = "gh dash",
            dir = "git_dir",
            direction = "tab",
            on_open = function(t)
                vim.cmd("startinsert!")
                vim.api.nvim_buf_set_keymap(t.bufnr, "n", "q", "<cmd>close<CR>", { noremap = true, silent = true })
            end,
            on_close = function(t)
                vim.cmd("startinsert!")
            end,
            hidden = true,
        })

        local function _lazygit_toggle()
            dash:toggle()
        end

        vim.keymap.set("n", "<leader>pr", _lazygit_toggle, { noremap = true, silent = true })

        local on_exit = function(obj)
            print(obj.code)
            print(obj.signal)
            print(obj.stdout)
            print(obj.stderr)
        end
        vim.keymap.set('n', '<leader>cpr', function()
            vim.system(
                {
                    vim.o.shell,
                    vim.o.shellcmdflag,
                    "git status | head -1 | sed -rn 's/[^\\/]*\\/(AB)-([0-9]+)-(.*)/\\1#\\2 \\3/p' | tr '-' ' ' | xargs -I {} gh pr create -t {} -f"
                },
                {},
                on_exit)
        end)
    end,
}

