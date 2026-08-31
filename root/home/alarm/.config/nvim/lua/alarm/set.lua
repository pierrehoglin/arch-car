local vim = vim

--vim.opt.foldmethod = 'indent'
vim.opt.number = true
vim.opt.relativenumber = true

vim.opt.tabstop = 4
vim.opt.softtabstop = 4
vim.opt.shiftwidth = 4
vim.opt.expandtab = true

vim.opt.smartindent = true

vim.opt.wrap = false

vim.opt.guicursor = 'n-v-c-i:block-Cursor'

vim.opt.ignorecase = true
vim.opt.smartcase = true

vim.opt.cursorline = true

vim.opt.list = true
vim.opt.listchars = { trail = '·', tab = '>-' }

vim.opt.swapfile = false
vim.opt.backup = false
vim.opt.undodir = os.getenv("HOME") .. "/.vim/undodir"
vim.opt.undofile = true

vim.opt.termguicolors = true

vim.opt.scrolloff = 100
vim.opt.signcolumn = "yes"

vim.opt.background = 'dark'

vim.opt.updatetime = 50

vim.opt.diffopt:append("vertical")

--vim.opt.colorcolumn = '100'

