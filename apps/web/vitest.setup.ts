import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-cleans with test globals; we import from vitest explicitly.
afterEach(cleanup);
