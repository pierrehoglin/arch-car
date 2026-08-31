local function ColorMyPencils(color)
        vim.cmd.colorscheme(color)
        vim.cmd([[
        highlight Normal guibg=none
        highlight NormalNC guibg=none
        highlight NormalFloat guibg=none
        highlight TelescopeNormal guibg=none
        highlight TelescopeBorder guibg=none
        highlight NvimTreeNormal guibg=none
        highlight NvimTreeNormalNC guibg=none
        highlight SignColumn guibg=none
        highlight FoldColumn guibg=none
        highlight LineNr guibg=none
        highlight Title guibg=none
    ]])
end

return {
        {
                "EdenEast/nightfox.nvim",
                lazy = false,
                enabled = false,
                opts = {},
                config = function()
                        ColorMyPencils("carbonfox")
                end,
        },
        {
                "catppuccin/nvim",
                lazy = false,
                enabled = false,
                opts = {},
                config = function()
                        require("catppuccin").setup({
                                flavour = "mocha", -- latte, frappe, macchiato, mocha
                        })
                end,
        },
        {
                "navarasu/onedark.nvim",
                lazy = false,
                enabled = false,
                opts = {},
                config = function()
                        require('onedark').setup {
                                style = 'darker'
                        }
                        require('onedark').load()
                end,
        },
        {
                "folke/tokyonight.nvim",
                lazy = false,
                enabled = true,
                opts = {},
                config = function()
                        ColorMyPencils("tokyonight-night")
                end,
        },
        {
                "brenoprata10/nvim-highlight-colors",
                opts = {}
        }
}

