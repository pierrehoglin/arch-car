return {
    "nvim-tree/nvim-tree.lua",
    dependencies = {
        "nvim-tree/nvim-web-devicons",
    },

    config = function()
        local api = require('nvim-tree.api')

        local function my_on_attach(bufnr)
            local function opts(desc)
                return {
                    desc = "nvim-tree: " .. desc,
                    buffer = bufnr,
                    noremap = true,
                    silent = true,
                    nowait = true
                }
            end

            -- default mappings
            api.map.on_attach.default(bufnr)

            -- custom mappings
            vim.keymap.set("n", "<C-o>", function()
                local node = api.tree.get_node_under_cursor()
                vim.ui.open(node.absolute_path)
            end, opts("Open: External"))
        end

        require("nvim-tree").setup({
            sync_root_with_cwd = true,
            view = {
                width = 50,
            },
            actions = {
                open_file = {
                    quit_on_open = true,
                },
            },
            on_attach = my_on_attach,
        })

        vim.keymap.set("n", "<leader>tf", function()
            api.tree.find_file({
                open = true,
                focus = true,
                update_root = "<bang>"
            })
        end)
        vim.keymap.set("n", "<leader>fe", api.tree.toggle)
    end,
}

