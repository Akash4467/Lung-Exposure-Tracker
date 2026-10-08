/// <reference types="jest" />
import { emailError } from '../validate';

test.each(['ui.test1@example.com', 'a@b.co', 'first.last+tag@sub.example.in'])('%s is fine', (e) =>
  expect(emailError(e)).toBeNull(),
);

test.each(['ui.@example.com', 'a@b', 'no-at-sign.com', 'a@.com', 'two@@at.com', 'sp ace@x.com'])(
  '%s is rejected',
  (e) => expect(emailError(e)).toMatch(/valid email/),
);

test('empty is not an error yet', () => expect(emailError('  ')).toBeNull());
