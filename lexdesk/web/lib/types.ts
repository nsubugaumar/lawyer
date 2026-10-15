/* Shapes shared by several screens. */

export type Matter = {
  id: string;
  reference: string;
  title: string;
  client: string;
  client_name: string;
  practice_area: string;
  practice_area_display: string;
  status: string;
  status_display: string;
  description: string;
  court: string;
  case_number: string;
  judge: string;
  opposing_counsel: string;
  lead_lawyer: string | null;
  lead_lawyer_detail: { id: string; full_name: string; title: string } | null;
  team: { user: { id: string; full_name: string; title: string; role: string }; role: string }[];
  is_restricted: boolean;
  opened_on: string;
  next_event: { id: string; kind_display: string; title: string; starts_at: string; location: string } | null;
  /** On the matter team, so allowed to read the privileged file notes. */
  on_team: boolean;
};

export const PRACTICE_AREAS = [
  ["litigation", "Civil litigation"], ["criminal", "Criminal"], ["corporate", "Corporate & commercial"], ["land", "Land & conveyancing"],
  ["family", "Family & succession"], ["employment", "Employment"], ["immigration", "Immigration"], ["tax", "Tax"], ["ip", "Intellectual property"], ["other", "Other"],
];

/** Reminder lead times offered in settings, in minutes. */
export const COURT_CHOICES = [10080, 4320, 2880, 1440, 240, 120, 60, 30];
export const APPOINTMENT_CHOICES = [2880, 1440, 240, 120, 60, 30, 15];
