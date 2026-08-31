require('alarm.set')
require('alarm.remap')
require('alarm.lazy_init')

local vim = vim
vim.api.nvim_create_autocmd("TextYankPost", {
    desc = "Highlight text when yanking",
    group = vim.api.nvim_create_augroup("highlight-yank", { clear = true }),
    callback = function()
        vim.hl.on_yank()
    end,
})

