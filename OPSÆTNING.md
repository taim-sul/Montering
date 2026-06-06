# Smart Logistics Service App — Opsætningsvejledning

## Hvad du har fået
- `admin.html` — Administrator app
- `team.html` — Medarbejder/team app
- `admin-manifest.json` + `team-manifest.json` — PWA installer-filer
- Denne guide

---

## TRIN 1: Opret Firebase projekt

1. Gå til **https://console.firebase.google.com**
2. Klik **"Add project"** → navngiv det f.eks. `smart-logistics`
3. Deaktiver Google Analytics (unødvendigt) → **Create project**

### Aktiver Authentication
1. Venstre menu → **Authentication** → **Get started**
2. **Sign-in method** → **Email/Password** → Aktiver → **Save**
3. Gå til **Users** → **Add user**
   - Email: `taim@smartlogistics.dk`
   - Password: Vælg en stærk adgangskode (husk den — det er admin-login)

### Opret Firestore Database
1. Venstre menu → **Firestore Database** → **Create database**
2. Vælg **"Start in test mode"** (vi sikrer den bagefter)
3. Vælg en server lokation tæt på Danmark: **europe-west1** → **Done**

### Aktiver Storage
1. Venstre menu → **Storage** → **Get started**
2. Vælg **"Start in test mode"** → **Done**
3. Vælg europe-west1 igen

### Hent din Firebase konfiguration
1. Venstre menu → ⚙️ **Project Settings** → **Your apps**
2. Klik **</>** (Web app) → Navngiv den → **Register app**
3. Kopiér `firebaseConfig` objektet — du skal bruge det i næste trin

---

## TRIN 2: Indsæt Firebase konfiguration i apps

Åbn **admin.html** og **team.html** i en teksteditor.

Find denne blok i begge filer (der er én i hver):
```javascript
const FIREBASE_CONFIG = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  ...
```

Erstat med dine egne værdier fra Firebase Console.

---

## TRIN 3: Skift adgangskoder

### Admin password
I `admin.html`, find:
```javascript
const ADMIN_PASSWORD = "admin123"; // Change this!
```
Erstat med den adgangskode du valgte i Authentication-trinnet ovenfor.

### Team passwords
I **begge** filer (`admin.html` og `team.html`), find:
```javascript
const TEAMS = [
  { id: "team1", name: "Team 1", password: "team1pass", color: "#E86B3E" },
  ...
```
Skift `password` for hvert team til noget sikkert.

---

## TRIN 4: Aktiver automatisk email (Firebase Extension)

Email sendes automatisk til `taim@smartlogistics.dk` når en rapport indsendes.

1. Gå til Firebase Console → **Extensions**
2. Find og installer: **"Trigger Email from Firestore"**
3. Under opsætning:
   - SMTP connection URI: `smtps://din@email.dk:password@smtp.gmail.com`
   - Eller brug SendGrid/Mailgun (anbefales til professionel brug)
4. **Email documents collection**: `mail` (matcher hvad appen skriver til)

> **Alternativ uden extension:** Brug EmailJS (gratis op til 200 emails/måned):
> - Opret konto på emailjs.com
> - Erstat `sendEmailNotification()` funktionen i `team.html` med EmailJS kald

---

## TRIN 5: Host filerne

Du skal have en webserver til at hoste filerne. Gratis muligheder:

### Firebase Hosting (anbefalet — integreret)
```bash
npm install -g firebase-tools
firebase login
firebase init hosting
# Kopiér admin.html, team.html, manifest-filer til public/ mappen
firebase deploy
```
Dine apps er nu på:
- `https://dit-projekt.web.app/admin.html`
- `https://dit-projekt.web.app/team.html`

### Alternativ: Netlify (drag-and-drop)
1. Gå til **netlify.com**
2. Træk din projektmappe direkte ind på siden
3. Du får en gratis URL med det samme

---

## TRIN 6: Tilføj app-ikoner

Du skal bruge to ikoner:
- `icon-192.png` (192×192 pixels)
- `icon-512.png` (512×512 pixels)

Opret dem via **https://realfavicongenerator.net** og placer dem i samme mappe som HTML-filerne.

---

## TRIN 7: Installer som app på mobilerne

### iPhone/iPad (Safari)
1. Åbn `admin.html` eller `team.html` i **Safari**
2. Tryk på **Del-ikonet** (firkant med pil op)
3. Vælg **"Føj til hjemmeskærm"**
4. App-ikonet vises nu på startskærmen

### Android (Chrome)
1. Åbn URL i **Chrome**
2. Chrome viser automatisk en banner "Installer app"
3. Eller: Menu (⋮) → **"Tilføj til startskærm"**

---

## Firestore sikkerhedsregler (VIGTIGT inden produktion)

Gå til Firestore → **Rules** og erstat med:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow read, write: if request.auth != null;
    }
    match /reports/{reportId} {
      allow read, write: if request.auth != null;
    }
    match /locations/{teamId} {
      allow read, write: if request.auth != null;
    }
    match /mail/{mailId} {
      allow write: if true; // Email queue
      allow read: if request.auth != null;
    }
  }
}
```

---

## Daglig arbejdsgang

1. **Admin** uploader PDF'er → tildeler teams → sætter dato
2. **Teams** logger ind næste morgen → ser deres opgaver
3. **Ved ankomst**: Tag før-billeder → tryk "Jeg er ankommet"
4. **Under arbejdet**: Tag efter-billeder
5. **Udfyld rapport**: Status, tid, underskrifter
6. **Email sendes automatisk** til taim@smartlogistics.dk
7. **Admin** kan se alt i realtid

---

## Support & næste skridt

- GPS-kort: Tilføj Google Maps API key i admin.html (markeret med kommentar)
- Ansvarsfraskrivelse PDF: Upload din PDF og link til den i disclaimerCard-sektionen
- Tilføj/fjern teams: Rediger TEAMS-arrayet i begge HTML-filer
