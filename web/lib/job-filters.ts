export type FilterState = { query: string; skill: string; aiOnly: boolean; page: number };
export type FilterAction =
  | { type: "query"; value: string }
  | { type: "skill"; value: string }
  | { type: "aiOnly"; value: boolean }
  | { type: "page"; value: number }
  | { type: "clear" };

export const initialFilters: FilterState = { query: "", skill: "", aiOnly: false, page: 1 };

export function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case "query": return { ...state, query: action.value, page: 1 };
    case "skill": return { ...state, skill: action.value, page: 1 };
    case "aiOnly": return { ...state, aiOnly: action.value, page: 1 };
    case "page": return { ...state, page: Math.max(1, action.value) };
    case "clear": return initialFilters;
  }
}
