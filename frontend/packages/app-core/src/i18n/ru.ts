/** All UI copy. Strings marked TODO(design) are placeholders taken from the Figma file. */
export const ru = {
  welcome: {
    text: "Приветственный текст", // TODO(design): real copy
    product: "рассказываем клиенту о продукте и фичах", // TODO(design): real copy
    telegramNote: "Регистрация пройдет в телеграмме",
    register: "Зарегистрироваться",
    waiting: "Ждём подтверждения…",
    reopenTelegram: "Открыть Telegram ещё раз",
    cancel: "Отмена",
    errors: {
      expired: "Ссылка для входа устарела. Попробуйте ещё раз.",
      failed: "Не получилось войти. Попробуйте ещё раз.",
      offline: "Нет соединения. Проверьте интернет и попробуйте ещё раз.",
    },
  },
  magicLink: {
    signingIn: "Входим…",
    expired: "Ссылка устарела или уже использована.",
    loginViaTelegram: "Войти через Telegram",
  },
  offline: {
    text: "Нет соединения с сервером.",
    retry: "Повторить",
  },
  stub: {
    onboarding: "Онбординг появится на следующем шаге (M2).",
    home: "Главный экран появится на следующем шаге (M2).",
    continue: "Дальше",
    signOut: "Выйти",
  },
} as const;
