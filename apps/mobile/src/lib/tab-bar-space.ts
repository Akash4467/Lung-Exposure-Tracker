import { createContext } from 'react';

/** Extra bottom space a screen needs inside the tabs so the floating glass bar doesn't hide
 * its last content (0 outside the tabs). Provided by app/(app)/(tabs)/_layout.tsx. */
export const TabBarSpace = createContext(0);
