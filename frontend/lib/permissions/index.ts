// Role → what the UI may offer. The backend computes `allowed_actions` (API_CONTRACT §4);
// this mirror only decides which controls to render, never authorizes anything.

export type Role = "owner" | "admin" | "analyst" | "viewer";
export type Permission = "view" | "approve" | "execute" | "manage_integrations" | "manage_team" | "manage_billing";

export const ROLE_LABEL: Record<Role, string> = {
  owner: "Владелец",
  admin: "Администратор",
  analyst: "Аналитик",
  viewer: "Наблюдатель",
};

export const PERMISSION_LABEL: Record<Permission, string> = {
  view: "Просмотр данных и рекомендаций",
  approve: "Подтверждение рекомендаций",
  execute: "Применение изменений в кабинете",
  manage_integrations: "Подключение кабинетов",
  manage_team: "Управление командой",
  manage_billing: "Тариф и оплата",
};

const MATRIX: Record<Role, Permission[]> = {
  owner: ["view", "approve", "execute", "manage_integrations", "manage_team", "manage_billing"],
  admin: ["view", "approve", "execute", "manage_integrations", "manage_team"],
  analyst: ["view", "approve"],
  viewer: ["view"],
};

export const can = (role: Role, p: Permission) => MATRIX[role].includes(p);
