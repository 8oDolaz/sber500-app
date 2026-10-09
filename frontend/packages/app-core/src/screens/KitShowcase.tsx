import { Button, Card, Chip, List, ListRow, Logo, Screen, SectionTitle, WelcomeText } from "@kainem/ui-kit";
import { useState } from "react";

/** Dev-only page to eyeball tokens and components against the Figma frames. */
export function KitShowcase() {
  const [done, setDone] = useState(false);
  return (
    <Screen>
      <Logo size="xl" />
      <WelcomeText>Приветственный текст</WelcomeText>
      <div className="kn-stack" style={{ marginTop: 32 }}>
        <Card minHeight={147}>Регистрация пройдет в телеграмме</Card>
        <Button>Зарегистрироваться</Button>
        <Button loading>Загрузка</Button>
        <Button disabled>Недоступно</Button>
        <Logo size="m" />
        <div>
          <Chip>Как пользоваться</Chip>
        </div>
        <section>
          <SectionTitle>Задачи</SectionTitle>
          <Card variant="home" minHeight={222}>
            <List>
              <ListRow done={done} onToggle={() => setDone(!done)} toggleLabel="Выполнено" meta="до 26.09">
                забрать посылку
              </ListRow>
              <ListRow />
              <ListRow />
            </List>
          </Card>
        </section>
        <a className="kn-link" href="#">
          https://t.me/kainem_bot
        </a>
      </div>
    </Screen>
  );
}
