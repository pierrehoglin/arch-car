return {
    "stevearc/conform.nvim",
    opts = {},
    config = function()
        require("conform").setup({
            async = true,
            formatters_by_ft = {
                -- cs = { "csharpier" },
                lua = { "stylua" },
                css = { "prettier" },
                scss = { "prettier" },
                javascript = { "prettier" },
                typescript = { "prettier" },
                typescriptreact = { "prettier" },
            },
            default_format_opts = {
                lsp_format = 'fallback'
            }
            -- formatters = {
            --     csharpier = {
            --         command = "csharpier",
            --         args = {
            --             "format",
            --             "--write-stdout"
            --         },
            --         to_stdin = true
            --     }
            -- }
        })
    end,
}

