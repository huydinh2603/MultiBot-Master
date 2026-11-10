import { PermissionFlagsBits } from 'discord.js';
import { AMMO, COMBAT, STAR_MODIFIERS } from '../config.js';
import { getUserData, queries } from '../database.js';

/**
 * Execute a shoot action between attacker and target
 */
export async function executeShoot(attacker, targetMember, ammoKey) {
  const ammoConfig = AMMO[ammoKey];
  if (!ammoConfig) {
    return { success: false, message: 'Loại đạn không hợp lệ.' };
  }

  const attackerId = attacker.id;
  const targetId = targetMember.id;

  // Cannot shoot bots or oneself
  if (targetMember.user.bot) {
    return { success: false, message: 'Không thể bắn bot.' };
  }
  if (attackerId === targetId) {
    return { success: false, message: 'Không thể tự bắn chính mình.' };
  }

  // Check attacker ammo inventory
  const ammoStock = queries.getAmmo.get(attackerId, ammoConfig.tier);
  if (!ammoStock || ammoStock.quantity <= 0) {
    return { success: false, message: `Bạn không có ${ammoConfig.name} trong túi đồ.` };
  }

  // Check if target is already currently muted
  if (targetMember.communicationDisabledUntilTimestamp && targetMember.communicationDisabledUntilTimestamp > Date.now()) {
    const remainingMin = Math.ceil((targetMember.communicationDisabledUntilTimestamp - Date.now()) / 60000);
    return { 
      success: false, 
      message: `<@${targetId}> hiện đang bị mute (còn ${remainingMin} phút). Không thể bắn thêm.` 
    };
  }

  // Check target immunity (30s grace period)
  const targetUser = getUserData(targetId);
  const now = Date.now();
  if (targetUser.immunity_until && targetUser.immunity_until > now) {
    const remainingSec = Math.ceil((targetUser.immunity_until - now) / 1000);
    return { 
      success: false, 
      message: `<@${targetId}> đang trong thời gian bảo hộ (còn ${remainingSec}s). Đạn không bị mất.` 
    };
  }

  // 1. Kiểm tra Chủ Server (Server Owner không thể bị mute theo cơ chế Discord)
  if (targetId === targetMember.guild?.ownerId) {
    return {
      success: false,
      message: `Không thể bắn Chủ Server (<@${targetId}>). Discord quy định Chủ Server miễn nhiễm hoàn toàn với Timeout/Mute. Đạn không bị mất.`,
    };
  }

  // 2. Kiểm tra quyền Quản trị viên (Discord cấm mute bất kỳ ai có quyền Administrator)
  if (targetMember.permissions.has(PermissionFlagsBits.Administrator)) {
    return {
      success: false,
      message: `Không thể bắn <@${targetId}> vì người này có quyền Quản trị viên (Administrator). Discord không cho phép mute Administrator. Đạn không bị mất.`,
    };
  }

  // 3. Kiểm tra quyền hạn và thứ bậc Role của Bot
  const botMember = targetMember.guild?.members?.me;
  if (botMember) {
    if (!botMember.permissions.has(PermissionFlagsBits.ModerateMembers) && !botMember.permissions.has(PermissionFlagsBits.Administrator)) {
      return {
        success: false,
        message: `Bot chưa được bật quyền "Hạn chế thời gian hoạt động của thành viên" (Moderate Members / Timeout) trong Cài đặt Server > Vai trò. Đạn không bị mất.`,
      };
    }

    if (targetMember.roles.highest.comparePositionTo(botMember.roles.highest) >= 0) {
      return {
        success: false,
        message: `Vai trò (Role) của Bot phải được kéo nằm trên vai trò cao nhất của <@${targetId}> trong danh sách Vai trò của Server. Đạn không bị mất.`,
      };
    }
  }

  // Helper to mute member with Discord timeout
  const applyMute = async (durationMs) => {
    try {
      await targetMember.timeout(durationMs, `Sheriff combat: shot by ${attacker.username} with ${ammoConfig.name}`);
      // Immunity starts after mute expires
      const immunityExpiresAt = Date.now() + durationMs + COMBAT.IMMUNITY_DURATION_MS;
      queries.setImmunity.run(immunityExpiresAt, targetId);
      queries.recordHitGiven.run(Math.floor(durationMs / 1000), attackerId);
      queries.recordHitReceived.run(Math.floor(durationMs / 1000), targetId);
      return true;
    } catch (err) {
      console.error('Failed to apply timeout:', err);
      return false;
    }
  };

  // Trừ đạn của người bắn sau khi đã vượt qua các điều kiện kiểm tra
  queries.consumeAmmo.run(attackerId, ammoConfig.tier);
  queries.recordShot.run(attackerId);

  // Case 1: Target has NO armor
  if (targetUser.armor_tier === 0) {
    const muted = await applyMute(ammoConfig.muteDurationMs);
    if (!muted) {
      // Hoàn lại đạn nếu timeout gặp sự cố bất ngờ từ Discord API
      queries.addAmmo.run(attackerId, ammoConfig.tier, 1);
      return { 
        success: false, 
        message: `Không thể áp dụng mute lên <@${targetId}> (Lỗi từ Discord API). Đã hoàn lại 1 ${ammoConfig.name} vào kho của bạn.` 
      };
    }
    return {
      success: true,
      message: `<@${attackerId}> bắn trúng <@${targetId}> (không giáp) bằng ${ammoConfig.name}.\nMute: ${ammoConfig.muteLabel}.`,
    };
  }

  // Case 4: Target armor is completely broken (0 HP)
  if (targetUser.armor_durability <= 0) {
    const muted = await applyMute(ammoConfig.muteDurationMs);
    if (!muted) {
      queries.addAmmo.run(attackerId, ammoConfig.tier, 1);
      return { 
        success: false, 
        message: `Không thể áp dụng mute lên <@${targetId}> (Lỗi từ Discord API). Đã hoàn lại 1 ${ammoConfig.name} vào kho của bạn.` 
      };
    }
    return {
      success: true,
      message: `Giáp của <@${targetId}> đã vỡ. ${ammoConfig.name} bắn xuyên thẳng.\nMute: ${ammoConfig.muteLabel}.`,
    };
  }

  // Case 2: Penetration (Bullet Tier >= Armor Tier)
  if (ammoConfig.tier >= targetUser.armor_tier) {
    const collateralDamage = Math.min(targetUser.armor_durability, 40);
    const newDurability = targetUser.armor_durability - collateralDamage;
    queries.updateArmorDurability.run(newDurability, targetId);

    const muted = await applyMute(ammoConfig.muteDurationMs);
    if (!muted) {
      queries.addAmmo.run(attackerId, ammoConfig.tier, 1);
      return { 
        success: false, 
        message: `Không thể áp dụng mute lên <@${targetId}> (Lỗi từ Discord API). Đã hoàn lại 1 ${ammoConfig.name} vào kho của bạn.` 
      };
    }

    return {
      success: true,
      message: `<@${attackerId}> bắn xuyên Giáp T${targetUser.armor_tier} của <@${targetId}> bằng ${ammoConfig.name}.\nMute: ${ammoConfig.muteLabel} | Giáp mục tiêu: ${newDurability}/${targetUser.armor_max_durability} HP (-${collateralDamage}).`,
    };
  }

  // Case 3: Ricochet (Bullet Tier < Armor Tier)
  const baseDamage = ammoConfig.baseWearDamage;
  const reduction = STAR_MODIFIERS[targetUser.armor_stars] || 0;
  const actualDamage = Math.max(1, Math.round(baseDamage * (1 - reduction)));
  const newDurability = Math.max(0, targetUser.armor_durability - actualDamage);

  queries.updateArmorDurability.run(newDurability, targetId);
  queries.recordRicochet.run(targetId);

  const starSymbols = '*'.repeat(targetUser.armor_stars);
  const starDisplay = starSymbols ? ` [${starSymbols}]` : '';

  return {
    success: true,
    message: `Giáp T${targetUser.armor_tier}${starDisplay} của <@${targetId}> đã cản thành công ${ammoConfig.name} từ <@${attackerId}>.\nĐộ bền: ${newDurability}/${targetUser.armor_max_durability} HP (-${actualDamage}) | Không bị mute.`,
  };
}
