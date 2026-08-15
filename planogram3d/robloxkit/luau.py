"""Luau-скрипты, встраиваемые в сгенерированные place-файлы Roblox.

Сервер тренажёра повторяет механику веб-игры planogram3d: взять товар на
складе → пополнить стеллаж → обслужить кассу; за действия начисляются
баллы в leaderstats, объявления отправляются игрокам, а поощрения из
внешней системы (webapp planogram3d) приходят через MessagingService
на топик ``gourman-rewards``.
"""

TRAINING_SERVER = """\
-- Тренажёр персонала «Гурман» (сгенерировано planogram3d.robloxkit)
local Players = game:GetService("Players")
local MessagingService = game:GetService("MessagingService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local announce = ReplicatedStorage:WaitForChild("Announce")
local carrying = {}   -- [player] = число коробок

Players.PlayerAdded:Connect(function(player)
	local stats = Instance.new("Folder")
	stats.Name = "leaderstats"
	stats.Parent = player
	local points = Instance.new("IntValue")
	points.Name = "Баллы"
	points.Value = 0
	points.Parent = stats
	local served = Instance.new("IntValue")
	served.Name = "Обслужено"
	served.Value = 0
	served.Parent = stats
	carrying[player] = 0
	announce:FireClient(player,
		"🎓 Добро пожаловать в тренажёр! Возьмите товар на складе 📦")
end)

Players.PlayerRemoving:Connect(function(player)
	carrying[player] = nil
end)

local function addPoints(player, n, reason)
	local s = player:FindFirstChild("leaderstats")
	if s then s["Баллы"].Value += n end
	announce:FireClient(player, ("+%d баллов — %s"):format(n, reason))
end

local function hook(model, handler)
	for _, obj in ipairs(model:GetDescendants()) do
		if obj:IsA("ProximityPrompt") then
			obj.Triggered:Connect(function(player)
				handler(player, obj)
			end)
		end
	end
end

local ws = workspace
if ws:FindFirstChild("Storeroom") then
	hook(ws.Storeroom, function(player)
		carrying[player] = 3
		announce:FireClient(player, "📦 Взято 3 коробки — пополните полки!")
	end)
end
if ws:FindFirstChild("Gondolas") then
	hook(ws.Gondolas, function(player, promptObj)
		if (carrying[player] or 0) <= 0 then
			announce:FireClient(player, "Сначала возьмите товар на складе 📦")
			return
		end
		carrying[player] -= 1
		addPoints(player, 15, "выкладка: " ..
			promptObj.Parent.Parent.Name)
	end)
end
if ws:FindFirstChild("Checkout") then
	hook(ws.Checkout, function(player)
		local s = player:FindFirstChild("leaderstats")
		if s then s["Обслужено"].Value += 1 end
		addPoints(player, 25, "покупатель обслужен на кассе")
	end)
end
if ws:FindFirstChild("Fridges") then
	hook(ws.Fridges, function(player)
		addPoints(player, 20, "холодильник проверен")
	end)
end

-- поощрения из внешней системы planogram3d (Open Cloud → MessagingService)
pcall(function()
	MessagingService:SubscribeAsync("gourman-rewards", function(msg)
		local data = msg.Data
		for _, player in ipairs(Players:GetPlayers()) do
			if data.roblox_user == nil
				or player.Name == data.roblox_user then
				if data.points and player:FindFirstChild("leaderstats") then
					player.leaderstats["Баллы"].Value += data.points
				end
				announce:FireClient(player, ("🏆 %s: +%d баллов (%s)")
					:format(data.name or player.Name, data.points or 0,
						data.reason or "поощрение"))
			end
		end
	end)
end)
"""

ANNOUNCE_CLIENT = """\
-- Всплывающие объявления тренажёра (сгенерировано planogram3d)
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local announce = ReplicatedStorage:WaitForChild("Announce")
local gui = script.Parent
local frame = gui:WaitForChild("Toast")
local label = frame:WaitForChild("Text")
local queue = {}
local busy = false

local function show()
	if busy then return end
	local text = table.remove(queue, 1)
	if not text then return end
	busy = true
	label.Text = text
	frame.Visible = true
	task.delay(3, function()
		frame.Visible = false
		busy = false
		show()
	end)
end

announce.OnClientEvent:Connect(function(text)
	table.insert(queue, text)
	show()
end)
"""


def reward_config(levels) -> str:
    """ModuleScript с уровнями-сменами веб-тренажёра."""
    rows = []
    for i, lv in enumerate(levels, 1):
        rows.append(
            f'\t{{level = {i}, title = "{lv["title"]}", '
            f'goal = {lv["goal"]}, time = {lv["time"]}, '
            f'bonusPerStar = 100}},')
    body = "\n".join(rows)
    return ("-- Уровни-смены тренажёра (сгенерировано planogram3d)\n"
            "return {\n" + body + "\n}\n")


def planogram_data(store) -> str:
    """ModuleScript с реальной планограммой магазина."""
    from ..webapp.network import price_for
    out = ["-- Планограмма магазина (сгенерировано planogram3d)",
           "return {", f'\tstore = "{store.name}",', "\tgondolas = {"]
    for g in store.gondolas:
        out.append(f'\t\t{{name = "{g.name}", products = {{')
        for p in store.approved_planogram.by_gondola(g.gondola_id):
            product = store.product(p.sku)
            price = round(price_for(product.category, p.sku))
            out.append(f'\t\t\t{{sku = "{p.sku}", '
                       f'name = "{product.name}", price = {price}, '
                       f'facings = {p.facings}}},')
        out.append("\t\t}},")
    out += ["\t},", "}"]
    return "\n".join(out) + "\n"
