-- The python environment will write to this file to trigger a spawn
local cmd_file_path = ac.getFolder(ac.FolderID.ExtCfgUser) .. "/gym_spawn_cmd.txt"

-- Hardcoded track width profile for Barcelona (ks_barcelona-layout_gp)
-- Maps track progress (0.0 to 1.0) to the estimated track half-width in meters.
-- These are rough placeholder values; adjust them to match actual track boundaries!
local BARCELONA_HALF_WIDTHS = {
    { progress = 0.00, half_width = 6.0 }, -- Start/Finish straight (approx 12m wide)
    { progress = 0.20, half_width = 5.5 }, -- Turn 1-3 area
    { progress = 0.50, half_width = 5.0 }, -- Back straight / mid sector
    { progress = 0.80, half_width = 5.5 }, -- Stadium section
    { progress = 1.00, half_width = 6.0 }  -- Back to Start/Finish (must match 0.00)
}

local function get_barcelona_half_width_at_progress(progress)
    -- Ensure progress is wrapped safely between 0 and 1
    progress = math.fmod(progress, 1.0)
    if progress < 0 then progress = progress + 1.0 end

    -- Linearly interpolate between the closest mapped points
    for i = 1, #BARCELONA_HALF_WIDTHS - 1 do
        if progress >= BARCELONA_HALF_WIDTHS[i].progress and progress <= BARCELONA_HALF_WIDTHS[i + 1].progress then
            local p1, p2 = BARCELONA_HALF_WIDTHS[i], BARCELONA_HALF_WIDTHS[i + 1]
            local t = (progress - p1.progress) / (p2.progress - p1.progress)
            return p1.half_width + t * (p2.half_width - p1.half_width)
        end
    end
    return 5.5 -- Safe fallback
end

local function spawn_car_randomly(spline_min, spline_max, lateral_min, lateral_max)
    ac.log("Spawn requested: spline_min=" .. spline_min .. " max=" .. spline_max)
    -- 1. Sample track progress and lateral offset
    local progress = spline_min + math.random() * (spline_max - spline_min)
    local lateral_offset = lateral_min + math.random() * (lateral_max - lateral_min)

    -- Calculate dynamic track width for lateral offset using Barcelona-specific mapping
    local track_half_width = get_barcelona_half_width_at_progress(progress)
    
    -- CRITICAL FIX: ac.trackProgressToWorldCoordinate returns the AI RACING LINE, not the track center!
    -- Since the racing line often touches the extreme edges of the track, applying a full track-width
    -- lateral offset will push the car out of bounds (into grass or walls), causing an instant physics reset.
    -- We scale down the lateral offset drastically to ensure the car stays on the tarmac.
    local safe_lateral_scale = 0.25 -- Only allow moving 25% of the half-width away from the racing line
    local lat_m = lateral_offset * (track_half_width * safe_lateral_scale)

    ac.log("Calculated progress: " .. progress .. ", lat_m: " .. lat_m)

    -- 2. Get world position on spline
    -- Wait, what if trackProgressToWorldCoordinate is wrong or returns nil?
    -- Let's try getting it, and log it.
    local pos = ac.trackProgressToWorldCoordinate(progress, false)
    local pos_ahead = ac.trackProgressToWorldCoordinate(progress + 0.005, false)

    if pos == nil then
        ac.log("Error: pos is nil. Is ac.trackProgressToWorldCoordinate valid for this track?")
        return
    end
    if pos_ahead == nil then
        ac.log("Error: pos_ahead is nil.")
        return
    end

    ac.log("Pos: " .. tostring(pos) .. ", Pos Ahead: " .. tostring(pos_ahead))

    -- 3. Calculate direction (forward vector)
    local forward = vec3(pos_ahead.x - pos.x, pos_ahead.y - pos.y, pos_ahead.z - pos.z):normalize()

    -- 4. Calculate right vector for lateral offset (assuming y is up)
    local right = vec3(-forward.z, 0, forward.x):normalize()

    -- 5. Apply lateral offset and slight elevation drop
    -- Increased Y offset to 1.5 meters to prevent physics collision clipping and instant respawn
    local final_pos = vec3(pos.x + right.x * lat_m, pos.y + 1.5, pos.z + right.z * lat_m)
    
    ac.log("Final Pos: " .. tostring(final_pos) .. " Forward: " .. tostring(forward))

    -- 6. Set car position and direction
    if physics and physics.setCarPosition then
        if physics.setGentleStop then physics.setGentleStop(0, false) end
        
        -- Try passing nil for direction first, exactly like fasttravel
        physics.setCarPosition(0, final_pos, nil)
        
        ac.log("Called physics.setCarPosition with pos: " .. tostring(final_pos) .. " (direction nil)")
    else
        ac.log("Error: physics.setCarPosition is not available.")
    end
end

local function check_spawn_cmd()
    local f = io.open(cmd_file_path, "r")
    if not f then return end
    local content = f:read("*all")
    f:close()

    if content and content ~= "" then
        local s_min, s_max, l_min, l_max = content:match("(%S+)%s+(%S+)%s+(%S+)%s+(%S+)")
        if s_min and s_max and l_min and l_max then
            spawn_car_randomly(tonumber(s_min), tonumber(s_max), tonumber(l_min), tonumber(l_max))
        end
    end
    
    -- Delete the file after processing to prevent repeated spawns
    os.remove(cmd_file_path)
end

function script.update(dt)
    check_spawn_cmd()
end

function script.windowMain(dt)
    ui.text("Gym Teleport is Active")
    ui.text("Listening for spawn commands at:")
    ui.text(cmd_file_path)
    
    ui.separator()
    ui.text("--- DIAGNOSTICS ---")
    
    if ui.button("Test Random Track Spawn") then
        -- Test spawn at start of track
        spawn_car_randomly(0.0, 0.1, -0.5, 0.5)
    end
    
    if ui.button("Test Relative Teleport (+10m Fwd, +2m Up)") then
        local car = ac.getCar(0)
        if car then
            -- Teleport exactly 10 meters forward and 2 meters up from CURRENT position
            local new_pos = car.position + car.look * 10 + vec3(0, 2, 0)
            
            ac.log("DIAGNOSTIC: Attempting relative teleport to: " .. tostring(new_pos))
            
            if physics and physics.setCarPosition then
                if physics.setGentleStop then physics.setGentleStop(0, true) end
                physics.setCarPosition(0, new_pos, car.look)
                if physics.setGentleStop then physics.setGentleStop(0, false) end
                if physics.setCarVelocity then physics.setCarVelocity(0, vec3(0,0,0)) end
                ac.log("DIAGNOSTIC: Relative teleport function called successfully.")
            else
                ac.log("DIAGNOSTIC: No teleport function found.")
            end
        else
            ac.log("DIAGNOSTIC: Could not get car object.")
        end
    end
end