# МАЯК-47 — R3 · восстановление чистой сессии KAT-Coder V2.5

**Тип:** самодостаточный пакет для передачи модели в новый чат Colibri · **Дата:** 2026-11-01
**Режим:** Assisted Repair, а не независимый тест с нуля. **Статус:** пакет подготовлен; R3 ещё НЕ ВЫПОЛНЕН.
**Область:** C++ / Unreal Engine 5; проект `InteractionLab`. Точная минорная версия UE5 НЕ ЗАДАНА; если API зависит от версии, отметить эту зависимость.
**Источник кода:** исходный ответ KAT-Coder R2 (сохранён без изменений в `Documents/Reports/KAT-Coder-V2.5_MAYAK-47_round2_original_20261101.txt`).

## 1. Прочитай перед началом

Ты — KAT-Coder V2.5, но **это новая сессия без истории предыдущего диалога**. Ниже есть весь контекст, необходимый для продолжения.
Твои первые два раунда содержали рабочие идеи и ошибки Unreal Engine. Второй раунд получил независимый статус `REVISE / NOT COMPILATION-READY`. Мы не просим делать проект заново, а просим **исправить представленную ниже версию R2**.

**Важное ограничение:** у тебя может не быть доступа к локальным файлам, движку UE5, компилятору или интернету. Весь код уже приложен ниже; не пытайся читать файлы по путям, если инструменты реально не подключены. Не называй проверки, которых не выполнял. Не подменяй фактическую компиляцию самопроверкой текста.

**Цель:** выдать шесть полных согласованных файлов, устранить конкретные замечания и честно оценить, что ещё требуется проверить. Сохрани хорошее из R2: начальный свет включён, правильно инициализирован cooldown, положение света +35 Z, Line Trace из камеры, отсутствие Tick.

## 2. Неизменные требования эталона МАЯК-47 v1.0

1. Проект `InteractionLab`, макрос `INTERACTIONLAB_API`.
2. `AInteractionLabCharacter` взаимодействует по **нажатию E**.
3. Использовать **Enhanced Input**.
4. Обнаружение интерактивного актора **Line Trace вдоль взгляда камеры**.
5. Дистанция трассировки **ровно 425 см**.
6. Взаимодействие через полноценный **C++ Unreal Interface**.
7. `AInteractiveLamp` содержит `UStaticMeshComponent` и `UPointLightComponent`.
8. Первоначально свет включён; каждое успешное взаимодействие переключает его.
9. Источник света на **+35 см по локальной оси Z** относительно меша.
10. Повторное успешное взаимодействие **с той же лампой** не чаще раза в **0,35 с**.
11. **Не использовать Tick / Event Tick**.
12. Корректность `UObject`, `UPROPERTY`, `UFUNCTION`, компонентов, сборки, владения и времени жизни.

## 3. Восемь адресных замечаний независимого ревью — исправить все

**R3-01 · Неправильный UE Interface / UHT.** В `IInteractiveObject.h` стоит `UNINTERFACE(INTERACTIONLAB_API, IInteractiveObject)`. Это не штатное объявление интерфейса Unreal: требуется корректный `UINTERFACE` с отдельным `U...` классом, наследующим `UInterface`, и отдельный `I...` класс с `GENERATED_BODY()`. Соблюди порядок `.generated.h` и макрос экспорта для модуля. Объясни, почему старое объявление ошибочно.

**R3-02 · `BlueprintNativeEvent` не является обычным чисто виртуальным методом.** Строка `UFUNCTION(BlueprintNativeEvent, BlueprintCallable) virtual bool ToggleInteraction() = 0;` не соответствует способу UHT-генерации событий. Используй правильную декларацию отражаемого события, переопределение `_Implementation` в лампе и объясни разницу между ними. Не делай `BlueprintNativeEvent` обычной `= 0` функцией.

**R3-03 · Mapping Context применён не через ту подсистему.** `APlayerController::AddInputMappingContext(...)` — не стандартный способ регистрации Enhanced Input. Возьми локального игрока через PlayerController и `UEnhancedInputLocalPlayerSubsystem` (в соответствии с UE5 API); проверь null и регистрацию через `AddMappingContext` с приоритетом. Покажи необходимые заголовки и модуль `EnhancedInput`. Укажи, как обеспечить настройку при позднем назначении Controller, если применимо.

**R3-04 · Ошибка типов из-за `&&`.** `UWorld* World = GetWorld() && DefaultMappingContext` присваивает логический результат `bool` указателю. Раздели проверки и устрани ошибочную/неиспользуемую переменную. Просмотри остальные условия на аналогичные ошибки.

**R3-05 · Поле `CameraComponent` отсутствует.** Камера создаётся в `InteractionLabCharacter.cpp`, но в заголовке персонажа нет поля `UPROPERTY` и/или объявления класса компонента. Исправь владение и создание, добавь нужные типы и `#include`, включая полный тип `UCapsuleComponent` для `GetCapsuleComponent()`.

**R3-06 · Неверная диспетчеризация вызова Blueprint-интерфейса.** Прямой `Interactive->ToggleInteraction()` не обеспечивает корректный путь вызова BlueprintNativeEvent. Проверь реализацию через `ImplementsInterface(...StaticClass())`, затем используй генерируемую `IInteractiveObject::Execute_ToggleInteraction(...)`. Убедись, что будет работать с C++ и Blueprint-реализациями интерфейса.

**R3-07 · Момент нажатия E и единый Input Action.** `ETriggerEvent::Completed` обычно связан с завершением действия/отпусканием клавиши и не соответствует прямому требованию о нажатии. Выбери событие, реагирующее на нажатие (с учётом конфигурации триггеров). В R2 `InteractAction` создаётся в конструкторе через `CreateDefaultSubobject`, тогда как в редакторе предложено назначать отдельный `IA_Interact`; убедись, что привязанный Action и Action в `IMC` **один и тот же объект**. Напиши точные шаги настройки в редакторе.

**R3-08 · Согласованность файлов и зависимостей.** В R2 отсутствует явный `#include "EnhancedInputComponent.h"`, а также необходимый include капсулы; перечитай все используемые типы и `generated.h`. Проверь `Build.cs`, порядок подключения, сигнатуры override и существование каждого API. Не называй `InputAction.h` и `InputMappingContext.h` «новыми исправлениями» — они уже были в R2.

### Справочные материалы Epic Games (ссылки, не факт прочтения)

- Unreal Interfaces: https://dev.epicgames.com/documentation/unreal-engine/interfaces-in-unreal-engine
- Enhanced Input: https://dev.epicgames.com/documentation/unreal-engine/enhanced-input-in-unreal-engine
- Implementing Blueprint Interfaces: https://dev.epicgames.com/documentation/unreal-engine/implementing-blueprint-interfaces-in-unreal-engine

Если у тебя есть рабочий инструмент доступа к интернету, можешь сверить API по этим страницам. **Если инструмента нет, не заявляй, что открывал страницы.** Не придумывай API.

## 4. Исходный код раунда 2 — точная версия для исправления

**Код ниже приведён как оригинальная входная версия с ошибками, а не как утверждённое решение. Внутри блоков R2 ничего не исправлено.**

### IInteractiveObject.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "IInteractiveObject.generated.h"

// Интерфейс для объектов, с которыми можно взаимодействовать.
UNINTERFACE(INTERACTIONLAB_API, IInteractiveObject)
class INTERACTIONLAB_API IInteractiveObject
{
    GENERATED_BODY()

public:
    // Переключает состояние взаимодействия.
    // Возвращает true, если взаимодействие успешно выполнено.
    UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Interactive")
    virtual bool ToggleInteraction() = 0;
};
```

### InteractiveLamp.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "IInteractiveObject.h"
#include "InteractiveLamp.generated.h"

UCLASS()
class INTERACTIONLAB_API AInteractiveLamp : public AActor, public IInteractiveObject
{
    GENERATED_BODY()

public:
    AInteractiveLamp();

protected:
    virtual void BeginPlay() override;

public:
    virtual bool ToggleInteraction_Implementation() override;

private:
    UPROPERTY(VisibleDefaultsOnly, Category = "Lamp")
    UStaticMeshComponent* LightMesh;

    UPROPERTY(VisibleDefaultsOnly, Category = "Lamp")
    UPointLightComponent* LightSource;

    UPROPERTY(Transient)
    bool bIsLightOn;

    UPROPERTY(Transient)
    float LastToggleTime;

    static constexpr float MinToggleInterval = 0.35f;
};
```

### InteractiveLamp.cpp

```cpp
#include "InteractiveLamp.h"
#include "Components/StaticMeshComponent.h"
#include "Components/PointLightComponent.h"

AInteractiveLamp::AInteractiveLamp()
{
    PrimaryActorTick.bCanEverTick = false;

    LightMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("LightMesh"));
    RootComponent = LightMesh;

    LightSource = CreateDefaultSubobject<UPointLightComponent>(TEXT("LightSource"));
    LightSource->SetupAttachment(RootComponent);
    LightSource->SetRelativeLocation(FVector(0.f, 0.f, 35.f));

    // Первоначально свет включён.
    bIsLightOn = true;
    LightSource->SetVisibility(true);

    // Инициализируем отрицательным значением, чтобы первое взаимодействие
    // не было заблокировано cooldown'ом при старте игры.
    LastToggleTime = -MinToggleInterval;
}

void AInteractiveLamp::BeginPlay()
{
    Super::BeginPlay();
    // BeginPlay не вызывает ToggleInteraction — свет остаётся в начальном состоянии.
}

bool AInteractiveLamp::ToggleInteraction_Implementation()
{
    const float CurrentTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.f;
    if (CurrentTime - LastToggleTime < MinToggleInterval)
    {
        return false;
    }

    bIsLightOn = !bIsLightOn;
    LightSource->SetVisibility(bIsLightOn);
    LastToggleTime = CurrentTime;
    return true;
}
```

### InteractionLabCharacter.h

```cpp
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "IInteractiveObject.h"
#include "InteractionLabCharacter.generated.h"

class UInputMappingContext;
class UInputAction;

UCLASS()
class INTERACTIONLAB_API AInteractionLabCharacter : public ACharacter
{
    GENERATED_BODY()

public:
    AInteractionLabCharacter();

protected:
    virtual void BeginPlay() override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

    UFUNCTION()
    void OnInteract(const FInputActionValue& ActionValue);

private:
    UPROPERTY(EditDefaultsOnly, Category = "Input")
    UInputMappingContext* DefaultMappingContext;

    UPROPERTY(EditDefaultsOnly, Category = "Input")
    UInputAction* InteractAction;

    void TryInteract();

    static constexpr float InteractionMaxDistance = 425.f;
};
```

### InteractionLabCharacter.cpp

```cpp
#include "InteractionLabCharacter.h"
#include "IInteractiveObject.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "Engine/World.h"

AInteractionLabCharacter::AInteractionLabCharacter()
{
    PrimaryActorTick.bCanEverTick = false;

    CameraComponent = CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonCamera"));
    CameraComponent->SetupAttachment(GetCapsuleComponent());
    CameraComponent->bUsePawnControlRotation = true;

    InteractAction = CreateDefaultSubobject<UInputAction>(TEXT("InteractAction"));
}

void AInteractionLabCharacter::BeginPlay()
{
    Super::BeginPlay();

    if (APlayerController* PC = Cast<APlayerController>(GetController()))
    {
        if (UWorld* World = GetWorld() && DefaultMappingContext)
        {
            PC->AddInputMappingContext(DefaultMappingContext);
        }
    }
}

void AInteractionLabCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    Super::SetupPlayerInputComponent(PlayerInputComponent);

    if (UEnhancedInputComponent* EnhancedComp = Cast<UEnhancedInputComponent>(PlayerInputComponent))
    {
        if (InteractAction)
        {
            EnhancedComp->BindAction(InteractAction, ETriggerEvent::Completed, this,
                &AInteractionLabCharacter::OnInteract);
        }
    }
}

void AInteractionLabCharacter::OnInteract(const FInputActionValue& ActionValue)
{
    TryInteract();
}

void AInteractionLabCharacter::TryInteract()
{
    UWorld* World = GetWorld();
    if (!World) return;

    APlayerController* PC = Cast<APlayerController>(GetController());
    if (!PC) return;

    // Корректные API UE5 для получения позиции и поворота камеры.
    FVector Start = CameraComponent->GetComponentLocation();
    FRotator CamRot = CameraComponent->GetComponentRotation();
    FVector Direction = CamRot.Vector();
    FVector End = Start + Direction * InteractionMaxDistance;

    FHitResult Hit;
    FCollisionQueryParams Params(TEXT("InteractionTrace"), true, this);

    bool bHit = World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params);

    if (!bHit || !Hit.GetActor()) return;

    IInteractiveObject* Interactive = Cast<IInteractiveObject>(Hit.GetActor());
    if (!Interactive) return;

    Interactive->ToggleInteraction();
}
```

### Build.cs

```csharp
using UnrealBuildTool;

public class InteractionLab : ModuleRules
{
    public InteractionLab(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "InputCore",
            "EnhancedInput"
        });
    }
}
```

## 5. Требования к ответу R3

1. Сначала короткая таблица из **R3-01 … R3-08**: что было неверно, какой принцип API применён, где исправлено.
2. Затем **ПОЛНЫЕ, окончательные, взаимосогласованные** файлы: `IInteractiveObject.h`, `InteractiveLamp.h`, `InteractiveLamp.cpp`, `InteractionLabCharacter.h`, `InteractionLabCharacter.cpp`, `InteractionLab.Build.cs`. Если необходим отдельный `IInteractiveObject.cpp`, предоставь его и объясни зачем. Ни одного `...` вместо кода.
3. Дай точную настройку UE5: `IA_Interact` / `IMC_InteractionLab`, E, Character Blueprint, GameMode, настройки компонентов коллизии и света; как добиться работы без Tick.
4. Выполни собственное **проверяемое текстовое ревью**. Явно проверь `UINTERFACE`, UHT, `_Implementation`/`Execute_`, Enhanced Input, поле камеры, `#include`, первоначальное состояние, расстояние, cooldown и Input Action asset.
5. Таблица 12 исходных требований с расположением в коде и статусом. Указывай только `PASS (по тексту)`, `PARTIAL`, `FAIL`, `UNKNOWN`, `NOT RUN` — не выдавай это за сборку.
6. Отдельно перечисли непроверенное: **COMPILE = NOT RUN; UHT = NOT RUN; RUNTIME = NOT RUN**, если эти испытания фактически не были выполнены.

**Формат:** русский язык, минимум вводных слов, максимум конкретного кода. Не повторяй весь входной код ещё раз в объяснениях; только финальный результат. Если длины ответа не хватает, остановись на границе целого файла и явно отметь `ПРОДОЛЖЕНИЕ ТРЕБУЕТСЯ` с перечнем оставшихся файлов, не выдавай незавершённый ответ за окончательный.

**Важно:** это продолжение старого кейса, поэтому не заявляй «исправил всё» без проверки каждой строки и не утверждай запуск Unreal Engine, если его не было.

## 6. Для владельца / ChatGPT (не оценка модели)

- Передать KAT-Coder **весь текст этого файла** в новую независимую сессию Colibri. Просто путь к файлу не подойдёт, если нет файловых инструментов.
- Пакет предназначен для модели с контекстом 16 384 токена; история предыдущего чата не нужна. При меньшем `ctx` может потребоваться загрузка по частям.
- Полученный результат полностью сохранить как `R3 ORIGINAL`, затем независимо проверить и обновить досье №17 → краткую №17.1 → оценку №15 → тактический контекст №13.
- Не спутать **восстановление сессии** с успешным исправлением кода. Статус до получения ответа: `R3 PACKAGE READY / RESULT PENDING`.
