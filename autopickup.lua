-- Auto-Pickup Lost Items Script
-- Checks workspace._LostItems and pickups all items with ProximityPrompt called PickupPrompt

while true do
    if workspace._LostItems and #workspace._LostItems > 0 then
        for _, item in ipairs(workspace._LostItems:GetChildren()) do
            if item:IsA("ProximityPrompt") and item.Name == "PickupPrompt" then
                local character = game.Players.LocalPlayer.Character
                if character then
                    character:MoveTo(item.Parent.PrimaryPart.Position)
                    task.wait(0.5)
                    fireproximityprompt(item)
                    task.wait(1)
                end
            end
        end
    end
    task.wait(0.1)
end