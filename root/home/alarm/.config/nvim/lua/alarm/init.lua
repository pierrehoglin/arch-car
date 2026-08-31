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


vim.g.mapleader = " "

vim.keymap.set("n", "<leader>pv", vim.cmd.Ex, { desc = "Open Vertical file editor" })

vim.keymap.set("n", "<leader><cr>", ":so<cr>", { desc = "Reload vim config" })
vim.keymap.set("n", "<leader>cc", ":e ~/.config/nvim/lua/hoglin/init.lua<cr>", { desc = "Open vim config" })

--vim.keymap.set("t", "<Esc>", "<c-\\><c-n>", { noremap = true, desc = "Stop terminal input" })

vim.keymap.set("n", "<esc>", "<cmd>nohlsearch<cr>", { desc = "Clear search if escape in normal mode" })
--vim.keymap.set('n', '<c-q>', ':bp<cr>', { desc = 'Open previous buffer' })
--vim.keymap.set('n', '<c-e>', ':bn<cr>', { desc = 'Open next buffer' })
--vim.keymap.set('n', '<c-d>', ':bd<cr>', { desc = 'Close buffer' })

vim.keymap.set("v", "J", ":m '>+1<CR>gv=gv", { desc = "Move selected down" })
vim.keymap.set("v", "K", ":m '<-2<CR>gv=gv", { desc = "Move selected up" })

vim.keymap.set("n", "J", "mzJ`z", { desc = "Remove line break from row but keep cursor in place" })
vim.keymap.set("n", "n", "nzzzv", { desc = "Find result in middle of screen" })
vim.keymap.set("n", "N", "Nzzzv", { desc = "Find result in middle of screen" })
vim.keymap.set("n", "=ap", "ma=ap'a", { desc = "" })
--vim.keymap.set("n", "<leader>zig", "<cmd>LspRestart<cr>")

-- greatest remap ever
vim.keymap.set("x", "<leader>p", [["_dP]], { desc = "Paste over visual without losing existing buffer copy" })

-- next greatest remap ever : asbjornHaland
vim.keymap.set({ "n", "v" }, "<leader>y", [["+y]], { desc = "Yank to system clipboard" })
vim.keymap.set("n", "<leader>Y", [["+Y]], { desc = "Yank to end of line to system clipboard" })
vim.keymap.set("n", "<leader>P", [["+P]], { desc = "Past from system clipboard" })

vim.keymap.set({ "n", "v" }, "<leader>d", '"_d', { desc = "Delete to void registry" })

vim.keymap.set("n", "Q", "<nop>", { desc = "Quit without saving? do nothing instead" })
vim.keymap.set("n", "<leader>fd", function()
    require("conform").format({
        bufnr = 0,
        lsp_fallback = true,
        async = true,
    })
end, { desc = "LSP format document" })

--vim.keymap.set("n", "<C-f>", "<cmd>silent !tmux neww tmux-sessionizer<CR>", { desc = "" })
--vim.keymap.set("n", "<M-h>", "<cmd>silent !tmux-sessionizer -s 0 --vsplit<CR>", { desc = "" })
--vim.keymap.set("n", "<M-H>", "<cmd>silent !tmux neww tmux-sessionizer -s 0<CR>", { desc = "" })

--vim.keymap.set("n", "<C-k>", "<cmd>cnext<CR>zz", { desc = "Quick fix list navigation" })
--vim.keymap.set("n", "<C-j>", "<cmd>cprev<CR>zz", { desc = "" })
--vim.keymap.set("n", "<leader>k", "<cmd>lnext<CR>zz", { desc = "" })
--vim.keymap.set("n", "<leader>j", "<cmd>lprev<CR>zz", { desc = "" })
vim.keymap.set("n", "[d", vim.diagnostic.goto_prev, { desc = "Previous diagnostic" })
vim.keymap.set("n", "]d", vim.diagnostic.goto_next, { desc = "Next diagnostic" })
vim.keymap.set("n", "<leader>e", vim.diagnostic.open_float, { desc = "Show diagnostic" })
vim.keymap.set("n", "<leader>q", vim.diagnostic.setloclist, { desc = "Diagnostics to loclist" })

vim.keymap.set({ "n", "i", "v" }, "<Left>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<Right>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<Down>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<Up>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<C-Left>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<C-Right>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<C-Down>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<C-Up>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<S-Left>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<S-Right>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<S-Down>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })
vim.keymap.set({ "n", "i", "v" }, "<S-Up>", "<Nop>", { noremap = true, silent = true, desc = "Do nothing" })

vim.keymap.set(
    "n",
    "<leader>s",
    [[:%s/\<<C-r><C-w>\>/<C-r><C-w>/gI<Left><Left><Left>]],
    { desc = "Replace current word" }
)
vim.keymap.set("n", "<leader>x", "<cmd>!chmod +x %<CR>", { silent = true }, { desc = "Make file executable" })



vim.api.nvim_create_autocmd("TextYankPost", {
    desc = "Highlight text when yanking",
    group = vim.api.nvim_create_augroup("highlight-yank", { clear = true }),
    callback = function()
        vim.hl.on_yank()
    end,
})

